# Contrato de datos

## Fuentes
Kaggle: jhonyjacobi/bank-attrition-detection. Versión 202611 (ver manifiesto_datos.json).
Ubicación: S3, versionado por fecha de corte (ver "Almacenamiento y versionamiento en S3").

## Almacenamiento y versionamiento en S3

Un bucket del equipo, con versionado de objetos activado, cuyo nombre vive en `MLOPS_DATA_BUCKET`
(`.env` en local, GitHub Secrets/Variables en Actions). Nunca se escribe en el repositorio.

```
s3://<bucket>/
├── raw/202611/                 # crudos de Kaggle tal cual; una carpeta por entrega (yyyymm)
├── features/202611/            # train.parquet, oot.parquet y <split>_lineage.json
├── scores/<codmes>/scores.csv  # salida de la inferencia batch
└── monitoring/<codmes>/psi_variables.csv
```

Dos niveles de versión:
- **Entrega de datos** (`raw/<yyyymm>/`): inmutable. Si cambian los datos, se crea una carpeta nueva,
  se actualizan `data_version` y `raw_path` en `config/config.yaml` y el manifiesto.
- **Objeto** (`VersionId` de S3): `docs/manifiesto_datos.json` guarda el SHA-256 y el `VersionId`
  de cada archivo. `features.py` rechaza leer un archivo cuyo SHA-256 no coincida con el manifiesto.

Trazabilidad: cada ejecución de features escribe `<split>_lineage.json` (URI, `VersionId` y SHA-256
de los crudos y de las features). Cada run de MLflow de entrenamiento y batch registra los tags
`data_version`, `data_path`, `data_sha256`, `data_s3_version_id` y `raw_path`; el de entrenamiento
guarda además el linaje completo como artefacto `data/train_lineage.json`.

### Preparar el bucket (una vez por equipo)

```bash
export MLOPS_DATA_BUCKET=<nombre-unico-del-bucket>   # también en .env
aws s3api create-bucket --bucket "$MLOPS_DATA_BUCKET" --region us-east-1
aws s3api put-bucket-versioning --bucket "$MLOPS_DATA_BUCKET" \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket "$MLOPS_DATA_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

### Subir una entrega y generar features

```bash
# Los CSV de Kaggle en data/raw/202611/ (excluidos de Git)
python -m bank_attrition.data subir --origen data/raw/202611
python -m bank_attrition.features --split train
python -m bank_attrition.features --split oot
```

`subir` valida SHA-256 y filas contra el manifiesto antes de escribir, no sobrescribe un objeto
existente con otro contenido, es idempotente y completa `source_uri` y `version_id` en
`docs/manifiesto_datos.json`. Hay que commitear el manifiesto actualizado.

## Esquema y llaves
- Clientes: 1 fila por `ID_CORRELATIVO` (único). Variables `_MENOS0..5` = últimos 6 meses.
- Requerimientos: N filas por cliente; llave `ID_CORRELATIVO`, periodo `CODMES`.
- Target: `ATTRITION` (1 = fuga en los próximos 6 meses). Tasa en train: 15.5 %.

## Política temporal
- `CODMES` de clientes train = 201208 (inconsistente con requerimientos 202403–202407).
  Se asume corte de train = 202407. [Pendiente confirmación docente]
- Corte OOT = 202408.
- Ventana de requerimientos: 5 meses hasta el corte (train 202403–202407; OOT 202404–202408)
  para que train y OOT tengan la misma ventana.

## Preparación
- Agregación de requerimientos a 1 fila por cliente: conteos por tipo, dictamen, top-5 producto
  y top-5 submotivo (top calculado en train), meses desde el último requerimiento.
- Clientes sin requerimientos: conteos = 0 y `FLG_TIENE_REQ` = 0 (≈50 % en train).
- Nulos: numéricas → mediana de train; categóricas → "MISSING". DICTAMEN nulo → "SIN_DICTAMEN".

## Limitaciones
- OOT sin etiqueta; el desempeño real solo se conoce 6 meses después.
- Muestra (`_sample`) del universo real.
