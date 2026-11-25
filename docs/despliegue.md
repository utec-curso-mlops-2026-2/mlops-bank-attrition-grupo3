# Despliegue y operación

Guía para instalar, configurar, entrenar, desplegar y operar la solución.
La infraestructura AWS y cómo recrearla están en [`infra/aws/`](../infra/aws/README.md).

## 1. Requisitos

| Recurso | Uso |
|---|---|
| Python 3.11 – 3.13 | Ejecución local y en GitHub Actions (3.12) |
| Cuenta de AWS personal (`us-east-2`) | Bucket S3, ECR, Lambda, EventBridge Scheduler, CloudWatch |
| AWS CLI ≥ 2.32 (`aws login --profile mlops-personal --region us-east-2`) | Acceso local sin guardar claves en el repo. Desde Python requiere `botocore[crt]`, incluido en `.[dev]` |
| Docker | Solo para construir la imagen de inferencia a mano (el CD la construye en GitHub) |
| Workspace de Databricks + token | MLflow Tracking y Model Registry (Unity Catalog) |
| Dataset de Kaggle `jhonyjacobi/bank-attrition-detection` | Datos crudos |

## 2. Instalación local

```bash
git clone https://github.com/utec-curso-mlops-2026-2/mlops-bank-attrition-grupo3.git
cd mlops-bank-attrition-grupo3
python -m venv .venv
# Linux/Mac: source .venv/bin/activate   |   Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env    # completar los valores
```

## 3. Configuración

- **Parámetros del pipeline:** `config/config.yaml` (rutas, cortes, hiperparámetros, umbrales).
- **Entorno local:** `.env` (excluido de Git). Variables descritas en el [README](../README.md#4-requisitos-y-configuración).
- **GitHub Actions** (`Settings → Secrets and variables → Actions`):

| Secret / Variable | Tipo | Uso |
|---|---|---|
| `DATABRICKS_HOST` | Secret | Workspace de MLflow |
| `DATABRICKS_TOKEN` | Secret | Autenticación en Databricks |
| `MLOPS_DATA_BUCKET` | Variable | Bucket S3 (`mlops-bank-attrition-grupo3-484815418393`) |
| `AWS_REGION` | Variable | `us-east-2` |
| `AWS_ROLE_ARN` | Variable | Rol `github-actions-mlops`, asumido por **OIDC**: no se guardan claves de AWS |

## 4. Preparación de datos (una vez por entrega)

```bash
# Crear el bucket con versionado y bloqueo público: ver docs/contrato_datos.md
python -m bank_attrition.data subir --origen data/raw/202611
python -m bank_attrition.features --split train
python -m bank_attrition.features --split oot
git add docs/manifiesto_datos.json && git commit -m "docs(datos): registrar entrega <yyyymm>"
```

Para una nueva entrega: crear `raw/<yyyymm>/`, actualizar `data_version`, `raw_path`,
`features.output_path` y `corte` en `config.yaml`, y el manifiesto.

## 5. Entrenamiento

- **Local:** `python -m bank_attrition.train`
- **GitHub Actions:** `Actions → Entrenamiento → Run workflow` sobre `develop` o `master`. También se
  dispara solo con cada push a `develop` que cambie `src/`, `config/` o `requirements.txt`.

Resultado: un run `training_pipeline` en MLflow y, si el modelo pasa la validación
(AUC test ≥ 0.70), una nueva versión con alias `champion` o `challenger`.

## 6. Inferencia batch

- **Local:** `python -m bank_attrition.batch`
- **AWS:** Lambda `bank-attrition-batch`, que recalcula las features OOT y ejecuta el batch.
  Ejecución manual:
  ```bash
  aws lambda invoke --function-name bank-attrition-batch --cli-read-timeout 900 \
    --payload '{"origen":"manual"}' --cli-binary-format raw-in-base64-out salida.json
  ```
- **Programación:** EventBridge Scheduler `bank-attrition-batch-mensual`, con `cron(0 6 1 * ? *)` en
  `America/Lima` (día 1 de cada mes a las 06:00). Para cambiarla, ejecutar `deploy.sh` con
  `BATCH_CRON='cron(...)'`.

Salidas en `s3://<bucket>/scores/<codmes>/scores.csv` y `s3://<bucket>/monitoring/<codmes>/psi_variables.csv`.

## 7. Inferencia online

- **Local:** `uvicorn bank_attrition.api:app --host 0.0.0.0 --port 8000`
- **AWS:** Lambda `bank-attrition-api` con Function URL pública:
  `https://pogsqiglzkxpvjojqncmtxchse0xaswn.lambda-url.us-east-2.on.aws/`

Ejemplos de invocación en el [README](../README.md#6-cómo-invocar-el-endpoint).

## 8. Despliegue continuo

Al integrar un PR a `master`, `cd.yml` ejecuta:

1. **Pruebas:** `ruff` y `pytest`.
2. **Validación del modelo:** comprueba que el alias `champion` existe y que su `test_auc` ≥
   `min_auc_test`. Si no se cumple, no despliega.
3. **Imagen:** construye el `Dockerfile` en un runner ARM y la publica en ECR con el tag del commit.
4. **Despliegue:** [`infra/aws/deploy.sh`](../infra/aws/deploy.sh) actualiza las dos Lambdas, la
   Function URL y el schedule.
5. **Prueba de humo:** llama a `/health` y a `/predict` en la URL publicada, verifica que responda
   la versión validada y que una entrada inválida devuelva 422. Las respuestas quedan como
   artefacto.

Despliegue manual equivalente: ver [`infra/aws/README.md`](../infra/aws/README.md#despliegue-de-la-inferencia).

## 9. Logs y monitoreo

| Qué | Dónde |
|---|---|
| Runs de entrenamiento y batch, métricas, PSI | MLflow, experimento `/Shared/utec-bank-attrition` |
| Ejecuciones de CI / entrenamiento / CD | Pestaña *Actions* de GitHub |
| Logs del job batch y de la API | CloudWatch Logs: `/aws/lambda/bank-attrition-batch` y `/aws/lambda/bank-attrition-api` |
| Scores y reportes de drift | S3: `scores/` y `monitoring/` |

## 10. Permisos (mínimo privilegio)

- **S3:** `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` y `s3:GetObjectVersion` sobre el bucket del equipo.
- **GitHub Actions** (`github-actions-mlops`): S3 sobre el bucket del equipo; ECR, Lambda,
  Scheduler y Logs sobre los recursos `bank-attrition-*`; `iam:PassRole` solo sobre los roles
  `bank-attrition-*`.
- **Lambdas** (`bank-attrition-lambda-role`): escribir logs en `/aws/lambda/bank-attrition-*`, y
  leer y escribir en el bucket del equipo.
- **Scheduler** (`bank-attrition-scheduler-role`): solo `lambda:InvokeFunction` sobre
  `bank-attrition-batch`.
- Políticas completas en [`infra/aws/iam/`](../infra/aws/iam/).
- **Databricks:** token con acceso al experimento y al modelo registrado.

## 11. Costos y retiro de recursos

- Configurar una alerta en **AWS Budgets**.
- Apagar o eliminar endpoints y recursos de cómputo cuando no se usen, y volver a levantarlos para la demo.
- Lambda, Function URL y Scheduler **no tienen costo fijo**: solo se paga por invocación. No hay
  nada que apagar entre demos.
- Retirar todo al terminar el curso:
  ```bash
  aws scheduler delete-schedule --name bank-attrition-batch-mensual
  aws lambda delete-function --function-name bank-attrition-api
  aws lambda delete-function --function-name bank-attrition-batch
  aws ecr delete-repository --repository-name bank-attrition-inferencia --force
  aws logs delete-log-group --log-group-name /aws/lambda/bank-attrition-api
  aws logs delete-log-group --log-group-name /aws/lambda/bank-attrition-batch
  # Roles: github-actions-mlops, bank-attrition-lambda-role, bank-attrition-scheduler-role
  #   (aws iam delete-role-policy ... && aws iam delete-role ...)
  # Bucket versionado: vaciar todas las versiones y luego aws s3api delete-bucket
  ```
- S3 tiene costo bajo con este volumen de datos; las versiones antiguas de objetos también se cobran.

## 12. Recuperación ante fallos

| Situación | Acción |
|---|---|
| El nuevo modelo funciona mal en producción | Reasignar el alias `champion` a la versión anterior en el Model Registry. El batch la toma en su siguiente ejecución; para la API, relanzar `cd.yml` (`workflow_dispatch`). |
| Falla un despliegue | `deploy.sh` es idempotente: volver a ejecutar `cd.yml` o desplegar una imagen anterior de ECR con `IMAGE_URI=<tag anterior> bash infra/aws/deploy.sh`. |
| Falla el job batch | Revisar `/aws/lambda/bank-attrition-batch` en CloudWatch, corregir y ejecutarlo a mano con `aws lambda invoke`. La salida se reescribe para el mismo `codmes`, y el bucket conserva la versión anterior. |
| Se sobrescribe o borra un archivo en S3 | Recuperar la versión anterior gracias al versionado del bucket (`VersionId` en el manifiesto). |
| Se expone una credencial | Rotarla de inmediato y actualizar el Secret de GitHub. |
| El CI falla en un PR | El PR no se puede integrar; corregir en la misma rama `feature/*`. |
