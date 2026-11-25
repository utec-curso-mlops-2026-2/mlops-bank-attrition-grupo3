# Infraestructura AWS

Cuenta personal del equipo (`484815418393`, región fija `us-east-2`).

## Recursos

| Recurso | Nombre | Notas |
|---|---|---|
| Bucket S3 | `mlops-bank-attrition-grupo3-484815418393` | Versionado activo, acceso público bloqueado, cifrado SSE-S3 |
| Proveedor OIDC | `token.actions.githubusercontent.com` | Permite a GitHub Actions obtener credenciales temporales sin claves |
| Rol IAM | `github-actions-mlops` | Solo lo asumen las ramas `master` y `develop` de este repositorio |
| Rol IAM | `bank-attrition-lambda-role` | Rol de ejecución de las Lambdas: logs y lectura/escritura en el bucket |
| Rol IAM | `bank-attrition-scheduler-role` | Permite a EventBridge Scheduler invocar el batch |
| Repositorio ECR | `bank-attrition-inferencia` | Imagen arm64 común para la API y el batch; conserva las últimas 5 |
| Lambda | `bank-attrition-api` | API online (R8) con Function URL pública; 2 GB, 60 s |
| Lambda | `bank-attrition-batch` | Recalcula las features OOT y ejecuta el scoring y el drift (R7/R9); 3 GB, 15 min |
| Schedule | `bank-attrition-batch-mensual` | `cron(0 6 1 * ? *)` en America/Lima: el día 1 de cada mes a las 06:00 |

Los recursos de despliegue (Lambda, ECR, ECS, Scheduler, logs) usan el prefijo `bank-attrition-*`. Los permisos del rol están acotados a ese prefijo.

## Políticas

- [iam/github-actions-trust.json](iam/github-actions-trust.json) define quién puede asumir el rol (OIDC de GitHub, repositorio y ramas). La organización usa el formato *immutable subject* de GitHub (`repo:<org>@<org_id>/<repo>@<repo_id>:ref:...`); se consulta con `gh api repos/<org>/<repo>/actions/oidc/customization/sub`.
- [iam/github-actions-permissions.json](iam/github-actions-permissions.json) define qué puede hacer el rol.

## Despliegue de la inferencia

[deploy.sh](deploy.sh) crea o actualiza las dos Lambdas, la Function URL y el schedule a partir de una imagen ya publicada en ECR. Es idempotente. El workflow `cd.yml` lo ejecuta en cada merge a `master`, y también se puede correr a mano:

```bash
export AWS_PROFILE=mlops-personal AWS_REGION=us-east-2
R=484815418393.dkr.ecr.us-east-2.amazonaws.com
aws ecr get-login-password | docker login --username AWS --password-stdin $R
docker build --platform linux/arm64 -t $R/bank-attrition-inferencia:manual .
docker push $R/bank-attrition-inferencia:manual
set -a; . ./.env; set +a   # DATABRICKS_HOST, DATABRICKS_TOKEN, MLOPS_DATA_BUCKET
IMAGE_URI=$R/bank-attrition-inferencia:manual bash infra/aws/deploy.sh
```

Logs en CloudWatch: `/aws/lambda/bank-attrition-api` y `/aws/lambda/bank-attrition-batch`.

**Costos:** Lambda y Function URL solo cobran por invocación. Ningún recurso queda encendido.

## Recrear

```bash
aws login --profile mlops-personal --region us-east-2
export AWS_PROFILE=mlops-personal
B=mlops-bank-attrition-grupo3-484815418393

aws s3api create-bucket --bucket $B --create-bucket-configuration LocationConstraint=us-east-2
aws s3api put-bucket-versioning --bucket $B --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket $B --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
aws iam create-role --role-name github-actions-mlops \
  --assume-role-policy-document file://infra/aws/iam/github-actions-trust.json
aws iam put-role-policy --role-name github-actions-mlops --policy-name mlops-ci-cd \
  --policy-document file://infra/aws/iam/github-actions-permissions.json
```

## Configuración en GitHub

- **Variables:** `AWS_ROLE_ARN`, `AWS_REGION`, `MLOPS_DATA_BUCKET`.
- **Secrets:** `DATABRICKS_HOST`, `DATABRICKS_TOKEN`.

Para usar credenciales de `aws login` desde Python en local hace falta `botocore[crt]`, incluido en `requirements-dev.txt`.
