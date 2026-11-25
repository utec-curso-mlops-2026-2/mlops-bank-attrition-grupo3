#!/usr/bin/env bash
# Despliega (crea o actualiza) la inferencia en AWS a partir de una imagen ya publicada en ECR:
#   - bank-attrition-api:   Lambda + Function URL pública (inferencia online, R8)
#   - bank-attrition-batch: Lambda invocada por EventBridge Scheduler (inferencia batch, R7)
# Es idempotente: se usa desde cd.yml y también a mano.
#
# Variables requeridas: IMAGE_URI, DATABRICKS_HOST, DATABRICKS_TOKEN, MLOPS_DATA_BUCKET
# Opcionales: AWS_REGION (us-east-2), BATCH_CRON, BATCH_TZ
set -euo pipefail

: "${IMAGE_URI:?Falta IMAGE_URI}"
: "${DATABRICKS_HOST:?Falta DATABRICKS_HOST}"
: "${DATABRICKS_TOKEN:?Falta DATABRICKS_TOKEN}"
: "${MLOPS_DATA_BUCKET:?Falta MLOPS_DATA_BUCKET}"
export AWS_REGION="${AWS_REGION:-us-east-2}"
BATCH_CRON="${BATCH_CRON:-cron(0 6 1 * ? *)}"   # día 1 de cada mes, 06:00
BATCH_TZ="${BATCH_TZ:-America/Lima}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
LAMBDA_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/bank-attrition-lambda-role"
SCHEDULER_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/bank-attrition-scheduler-role"
API_FN=bank-attrition-api
BATCH_FN=bank-attrition-batch
SCHEDULE=bank-attrition-batch-mensual
TAGS="proyecto=mlops-bank-attrition-grupo3"

ENV_JSON=$(python3 - <<EOF
import json, os
print(json.dumps({"Variables": {
    "DATABRICKS_HOST": os.environ["DATABRICKS_HOST"],
    "DATABRICKS_TOKEN": os.environ["DATABRICKS_TOKEN"],
    "MLFLOW_TRACKING_URI": "databricks",
    "MLFLOW_REGISTRY_URI": "databricks-uc",
    "MLFLOW_EXPERIMENT_NAME": "/Shared/utec-bank-attrition",
    "MLOPS_DATA_BUCKET": os.environ["MLOPS_DATA_BUCKET"],
}}))
EOF
)

exists() { aws lambda get-function --function-name "$1" >/dev/null 2>&1; }
wait_ready() { aws lambda wait function-updated-v2 --function-name "$1"; }

# deploy_fn <nombre> <handler> <memoria MB> <timeout s> <descripción>
deploy_fn() {
  local name=$1 handler=$2 memory=$3 timeout=$4 description=$5
  if exists "$name"; then
    echo "Actualizando $name"
    aws lambda update-function-code --function-name "$name" --image-uri "$IMAGE_URI" \
      --architectures arm64 >/dev/null
    wait_ready "$name"
    aws lambda update-function-configuration --function-name "$name" \
      --image-config "Command=$handler" --memory-size "$memory" --timeout "$timeout" \
      --environment "$ENV_JSON" --description "$description" >/dev/null
  else
    echo "Creando $name"
    aws lambda create-function --function-name "$name" --package-type Image \
      --code "ImageUri=$IMAGE_URI" --role "$LAMBDA_ROLE" --architectures arm64 \
      --image-config "Command=$handler" --memory-size "$memory" --timeout "$timeout" \
      --environment "$ENV_JSON" --description "$description" --tags "$TAGS" >/dev/null
    aws lambda wait function-active-v2 --function-name "$name"
  fi
  wait_ready "$name"
}

deploy_fn "$API_FN" bank_attrition.lambda_handlers.api_handler 2048 60 \
  "API online de probabilidad de fuga (R8)"
deploy_fn "$BATCH_FN" bank_attrition.lambda_handlers.batch_handler 3008 900 \
  "Scoring batch mensual y data drift (R7/R9)"

# Function URL pública para la API (la validación de entrada la hace FastAPI).
if ! aws lambda get-function-url-config --function-name "$API_FN" >/dev/null 2>&1; then
  aws lambda create-function-url-config --function-name "$API_FN" --auth-type NONE >/dev/null
  aws lambda add-permission --function-name "$API_FN" --statement-id url-publica \
    --action lambda:InvokeFunctionUrl --principal "*" --function-url-auth-type NONE >/dev/null
  aws lambda add-permission --function-name "$API_FN" --statement-id url-publica-invoke \
    --action lambda:InvokeFunction --principal "*" --invoked-via-function-url >/dev/null
fi
API_URL=$(aws lambda get-function-url-config --function-name "$API_FN" --query FunctionUrl --output text)

# Programación mensual del batch.
BATCH_ARN=$(aws lambda get-function --function-name "$BATCH_FN" --query Configuration.FunctionArn --output text)
TARGET=$(printf '{"Arn":"%s","RoleArn":"%s","Input":"{\\"origen\\":\\"eventbridge-scheduler\\"}","RetryPolicy":{"MaximumRetryAttempts":1}}' "$BATCH_ARN" "$SCHEDULER_ROLE")
if aws scheduler get-schedule --name "$SCHEDULE" >/dev/null 2>&1; then
  op=update-schedule
else
  op=create-schedule
fi
aws scheduler "$op" --name "$SCHEDULE" --schedule-expression "$BATCH_CRON" \
  --schedule-expression-timezone "$BATCH_TZ" --flexible-time-window Mode=OFF \
  --target "$TARGET" --description "Scoring batch mensual de fuga de clientes" >/dev/null

echo "API_URL=$API_URL"
echo "SCHEDULE=$SCHEDULE ($BATCH_CRON $BATCH_TZ)"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "api_url=$API_URL" >> "$GITHUB_OUTPUT"
fi
