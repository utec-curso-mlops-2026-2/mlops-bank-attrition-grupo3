# Despliegue y operación

Guía para instalar, configurar, entrenar, desplegar y operar la solución.
Las secciones marcadas con 🚧 se completarán cuando el despliegue en AWS se integre a `develop`.

## 1. Requisitos

| Recurso | Uso |
|---|---|
| Python 3.11 – 3.13 | Ejecución local y en GitHub Actions (3.12) |
| Cuenta de AWS personal | Bucket S3 y servicios de inferencia |
| AWS CLI con un perfil configurado (`aws configure` o SSO) | Acceso local a S3 sin guardar claves en el repo |
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
- **GitHub Actions:** las mismas variables como *Secrets* del repositorio
  (`Settings → Secrets and variables → Actions`):

| Secret / Variable | Tipo | Uso |
|---|---|---|
| `DATABRICKS_HOST` | Secret | Workspace de MLflow |
| `DATABRICKS_TOKEN` | Secret | Autenticación en Databricks |
| `MLOPS_DATA_BUCKET` | Secret o Variable | Bucket S3 |
| `AWS_REGION` | Variable | Región de AWS |
| Credenciales de AWS 🚧 | Secret / rol OIDC | `<completar: claves de un usuario IAM o rol asumido por OIDC>` |

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
- **GitHub Actions** 🚧: `Actions → train.yml → Run workflow`.

Resultado: un run `training_pipeline` en MLflow y, si el modelo pasa la validación
(AUC test ≥ 0.70), una nueva versión con alias `champion` o `challenger`.

## 6. Inferencia batch

- **Local:** `python -m bank_attrition.batch`
- **AWS** 🚧: `<completar: servicio, nombre del recurso, cómo ejecutarlo manualmente>`
- **Programación** 🚧: regla de EventBridge `<completar: nombre y expresión, p. ej. cron(0 10 1 * ? *) = día 1 de cada mes>`.

Salidas en `s3://<bucket>/scores/<codmes>/scores.csv` y `s3://<bucket>/monitoring/<codmes>/psi_variables.csv`.

## 7. Inferencia online

- **Local:** `uvicorn bank_attrition.api:app --host 0.0.0.0 --port 8000`
- **AWS** 🚧: `<completar: servicio y URL del endpoint>`

Ejemplos de invocación en el [README](../README.md#6-cómo-invocar-el-endpoint).

## 8. Despliegue continuo 🚧

Al integrar un PR a `master`, `cd.yml` `<completar: pasos, p. ej. construir la imagen, publicarla
en ECR, actualizar el job batch y el endpoint, y probar /health>`.

## 9. Logs y monitoreo

| Qué | Dónde |
|---|---|
| Runs de entrenamiento y batch, métricas, PSI | MLflow, experimento `/Shared/utec-bank-attrition` |
| Ejecuciones de CI / entrenamiento / CD | Pestaña *Actions* de GitHub |
| Logs del job batch y de la API 🚧 | CloudWatch Logs, `<completar: log groups>` |
| Scores y reportes de drift | S3: `scores/` y `monitoring/` |

## 10. Permisos (mínimo privilegio)

- **S3:** `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` y `s3:GetObjectVersion` sobre el bucket del equipo.
- **Inferencia** 🚧: `<completar: permisos del rol de ejecución (ECR, CloudWatch Logs, S3)>`.
- **Databricks:** token con acceso al experimento y al modelo registrado.

## 11. Costos y retiro de recursos

- Configurar una alerta en **AWS Budgets**.
- Apagar o eliminar endpoints y recursos de cómputo cuando no se usen, y volver a levantarlos para la demo.
- Recursos a retirar 🚧: `<completar: lista de recursos y comandos para eliminarlos>`.
- S3 tiene costo bajo con este volumen de datos; las versiones antiguas de objetos también se cobran.

## 12. Recuperación ante fallos

| Situación | Acción |
|---|---|
| El nuevo modelo funciona mal en producción | Reasignar el alias `champion` a la versión anterior en el Model Registry. Batch y API la toman sin cambiar código (la API requiere reinicio). |
| Falla el job batch | Revisar los logs, corregir y volver a ejecutarlo manualmente; la salida se sobrescribe para el mismo `codmes`. |
| Se sobrescribe o borra un archivo en S3 | Recuperar la versión anterior gracias al versionado del bucket (`VersionId` en el manifiesto). |
| Se expone una credencial | Rotarla de inmediato y actualizar el Secret de GitHub. |
| El CI falla en un PR | El PR no se puede integrar; corregir en la misma rama `feature/*`. |
