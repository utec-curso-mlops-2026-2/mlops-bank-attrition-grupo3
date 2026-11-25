# Infraestructura AWS

Cuenta personal del equipo (`484815418393`, región fija `us-east-2`).

## Recursos

| Recurso | Nombre | Notas |
|---|---|---|
| Bucket S3 | `mlops-bank-attrition-grupo3-484815418393` | Versionado activo, acceso público bloqueado, cifrado SSE-S3 |
| Proveedor OIDC | `token.actions.githubusercontent.com` | Permite a GitHub Actions obtener credenciales temporales sin claves |
| Rol IAM | `github-actions-mlops` | Solo lo asumen las ramas `master` y `develop` de este repositorio |

Los recursos de despliegue (Lambda, ECR, ECS, Scheduler, logs) usan el prefijo `bank-attrition-*`. Los permisos del rol están acotados a ese prefijo.

## Políticas

- [iam/github-actions-trust.json](iam/github-actions-trust.json) define quién puede asumir el rol (OIDC de GitHub, repositorio y ramas).
- [iam/github-actions-permissions.json](iam/github-actions-permissions.json) define qué puede hacer el rol.

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
