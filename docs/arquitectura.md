# Arquitectura

Este documento describe los componentes de la solución, cómo se conectan y qué los dispara.
Todos los componentes están implementados y desplegados en la cuenta AWS del equipo
(`484815418393`, región `us-east-2`). Lo único pendiente es el plan de model/concept drift, que se
propone en el informe técnico.

## 1. Vista general

```mermaid
flowchart TB
    subgraph DEV["Desarrollo – GitHub"]
        F["feature/*"] -->|"PR + 1 aprobación"| D["develop"]
        D -->|"PR release"| M["master"]
        CI["ci.yml<br/>ruff + pytest"]
        F -. "dispara en PR" .-> CI
        D -. "dispara en PR" .-> CI
    end

    subgraph DATA["Datos – Amazon S3 (versionado)"]
        RAW["raw/202611/"]
        FEAT["features/202611/<br/>train.parquet · oot.parquet<br/>*_lineage.json"]
        SC["scores/&lt;codmes&gt;/"]
        MO["monitoring/&lt;codmes&gt;/"]
    end

    subgraph ML["MLflow – Databricks"]
        TR["Tracking server<br/>experimento compartido"]
        RG["Model Registry (Unity Catalog)<br/>@champion · @challenger"]
    end

    subgraph INF["Inferencia – AWS us-east-2"]
        ECR["ECR<br/>bank-attrition-inferencia"]
        EB["EventBridge Scheduler<br/>bank-attrition-batch-mensual"]
        BJ["Lambda bank-attrition-batch<br/>features OOT + batch.py + PSI"]
        EP["Lambda bank-attrition-api<br/>Function URL · api.py"]
        CW["CloudWatch Logs"]
    end

    KAG["Kaggle<br/>CSV crudos"] -->|"data.py subir"| RAW
    RAW -->|"features.py"| FEAT
    TW["train.yml<br/>(OIDC → AWS)"] -->|"train.py"| TR
    FEAT --> TR
    TR -->|"AUC test ≥ 0.70"| RG

    M -->|"cd.yml: build + push"| ECR
    ECR -->|"deploy.sh"| BJ
    ECR -->|"deploy.sh"| EP
    EB --> BJ
    RG --> BJ
    RG --> EP
    FEAT --> BJ
    BJ --> SC
    BJ --> MO
    BJ --> TR
    BJ --> CW
    EP --> CW
    U["Sistema del asesor"] -->|"POST /predict"| EP
    RET["Área de retención"] -->|"lee scores"| SC
```

## 2. Componentes

### 2.1 Control de versiones – GitHub ✅

- Repositorio en la organización `utec-curso-mlops-2026-2`, creado desde la plantilla del curso.
- **Gitflow**: `feature/*` → `develop` → `master`. Las dos ramas principales tienen *rulesets*:
  integración solo por PR, al menos 1 aprobación de otro integrante y CI en verde.
- `.gitignore` excluye datos (`*.csv`, `*.parquet`, `data/`), modelos (`*.pkl`, `*.joblib`,
  `mlruns/`), entornos virtuales y credenciales (`.env`, `.aws/`, `*.pem`).

### 2.2 Datos y versionamiento – Amazon S3 ✅

- Bucket con **versionado de objetos** y **bloqueo de acceso público**. Su nombre vive en
  `MLOPS_DATA_BUCKET`, nunca en el código.
- **Dos niveles de versión:**
  - *Entrega* (`raw/<yyyymm>/`): carpeta inmutable por fecha de corte.
  - *Objeto* (`VersionId` de S3 + SHA-256): registrados en `docs/manifiesto_datos.json`.
- `features.py` rechaza leer un archivo cuyo SHA-256 no coincide con el manifiesto y escribe un
  `<split>_lineage.json` (crudos → features) para dar trazabilidad.
- Entrenamiento y batch consumen **las mismas features** desde `features/202611/`.
- Detalle en [`contrato_datos.md`](contrato_datos.md).

### 2.3 Pipeline de entrenamiento ✅

Scripts modulares en `src/bank_attrition/`, parametrizados con `config/config.yaml`:

1. **Cruce y features** (`features.py`): clientes + requerimientos de los últimos 5 meses.
2. **Split** train/test 70/30 estratificado, semilla 42 (`train.py`).
3. **Limpieza e imputación** (`preprocess.py`): `ColumnTransformer` ajustado solo con train. Va
   dentro del `Pipeline` de scikit-learn, por lo que **se reutiliza idéntico en batch y online**.
4. **3 modelos**: Regresión Logística, Random Forest y LightGBM.
5. **Selección** explícita por `test_auc` (`train.selection_metric`).
6. **Scoreo del OOT** en el pipeline batch.

Métricas (`evaluate.py`): AUC, Gini, KS y % de fugas capturadas en el top 10 % y 20 %.

### 2.4 Tracking y Model Registry – MLflow en Databricks ✅

- **Tracking server remoto** compartido (`MLFLOW_TRACKING_URI=databricks`), experimento
  `/Shared/utec-bank-attrition`.
- Run padre `training_pipeline` con un **run anidado por modelo**; `mlflow.sklearn.autolog`
  registra los hiperparámetros.
- Artefactos: curva ROC, matriz de confusión, importancia de variables y linaje de datos.
- Tags: `git_commit`, `author`, `data_version`, `data_path`, `data_sha256`, `data_s3_version_id`.
- El mejor modelo se registra con **signature**, **input example** y su entorno.
- **Criterio de promoción** (`promote()` en `train.py`):
  - AUC test < 0.70 → versión marcada `validation=rejected`, sin alias.
  - AUC test ≥ 0.70 y mejor que el `champion` actual → alias `champion`.
  - AUC test ≥ 0.70 pero no mejor → alias `challenger`.
- Batch y API cargan **siempre** `models:/<modelo>@champion`, nunca un archivo local.

### 2.5 Inferencia batch – AWS Lambda + EventBridge Scheduler ✅

- **Lógica** (`batch.py`): carga `@champion`, scorea el OOT y escribe en
  `s3://<bucket>/scores/<codmes>/scores.csv` las columnas `id_cliente`, `prob_fuga`, `decil`
  (1 = mayor riesgo), `segmento_riesgo` (alto/medio/bajo), `codmes_score`, `fecha_score` y
  `model_version`. Registra un run `batch_<codmes>` en MLflow con el linaje.
- **Ejecución en AWS**: la Lambda `bank-attrition-batch` (`batch_handler` en
  `lambda_handlers.py`) primero recalcula las features OOT desde S3 y después ejecuta `batch.run`.
  Usa 3 GB de memoria y tiene un timeout de 15 min; una ejecución real tarda unos 15 s y usa unos
  930 MB.
- **Programación**: EventBridge Scheduler (`bank-attrition-batch-mensual`) la invoca con
  `cron(0 6 1 * ? *)` en `America/Lima`, es decir el día 1 de cada mes a las 06:00. Usa el rol
  `bank-attrition-scheduler-role`, que solo puede invocar esa función.
- **Logs**: CloudWatch, en `/aws/lambda/bank-attrition-batch`.
- **Por qué Lambda**: el scoring de unos 14 000 clientes termina muy por debajo del límite de 15 min
  de Lambda. Se cobra solo por ejecución (una al mes), y no requiere VPC, cluster ni servidores
  encendidos. Se descartaron ECS Fargate (más piezas: cluster, red, task definition) y SageMaker
  Batch Transform (más caro y requiere empaquetar el modelo en su formato).

### 2.6 Inferencia online – AWS Lambda + Function URL ✅

- **Lógica** (`api.py`): API FastAPI que carga el modelo una sola vez al arrancar.
  - `GET /health`: estado, nombre y versión del modelo.
  - `POST /predict`: recibe el cliente y sus requerimientos en JSON, construye las features con la
    **misma función** que el pipeline (`build_features`) y devuelve `prob_fuga` y `model_version`.
  - Validación: `422` si falta un campo o tiene un tipo incorrecto; `400` si no se puede scorear.
- **Despliegue**: la Lambda `bank-attrition-api` usa `api_handler`, que adapta FastAPI con Mangum
  y carga el modelo una vez por contenedor. Está expuesta con una **Function URL** pública:
  `https://pogsqiglzkxpvjojqncmtxchse0xaswn.lambda-url.us-east-2.on.aws/`. Usa 2 GB de memoria y tiene un timeout de 60 s.
- **Latencia**: unos 25 s en *cold start*, por la descarga del modelo desde el Registry, y unos 1 s
  en caliente.
- **Por qué Lambda + Function URL**: el tráfico esperado (consultas puntuales del contact center)
  es bajo e intermitente, y Lambda solo cobra por invocación. Una Function URL da HTTPS sin
  configurar API Gateway. Se descartaron:
  - **SageMaker Endpoint**: tiene una instancia encendida 24/7, con costo fijo.
  - **ECS/App Runner**: requieren un contenedor siempre activo.
  - **API Gateway**: su límite de 29 s no tolera el cold start.
- **Imagen**: un solo `Dockerfile` (arm64) para la API y el batch, publicado en ECR
  (`bank-attrition-inferencia`). Cada función elige su handler con `ImageConfig.Command`.

### 2.7 Monitoreo

- **Data drift** ✅ (`monitoring.py`, como paso del batch): PSI por variable y sobre la distribución
  del score, train vs aplicación, con 10 bins. Semáforo: < 0.10 estable · 0.10–0.25 alerta ·
  > 0.25 crítico. El reporte se guarda en `s3://<bucket>/monitoring/<codmes>/psi_variables.csv` y en
  MLflow (`psi_score`, `n_vars_alerta`, `n_vars_critico`).
- **Model/concept drift**: plan propuesto en el informe técnico para cuando lleguen las etiquetas
  reales (6 meses después).

### 2.8 CI/CD – GitHub Actions

| Workflow | Disparador | Función | Estado |
|---|---|---|---|
| `ci.yml` | PR y push a `develop`/`master` | `ruff` + `pytest`; bloquea el PR si falla. Sube el reporte de pruebas como artefacto. | ✅ |
| `train.yml` | `workflow_dispatch` o push a `develop` (cambios en `src/`, `config/`, `requirements.txt`) | Features → entrenamiento + registro en MLflow → resumen. El linaje se publica como artefacto y los resultados pasan como outputs entre jobs. | ✅ |
| `cd.yml` | Integración a `master` | Pruebas → validación del `champion` → imagen en ECR → despliegue con `infra/aws/deploy.sh` → prueba de humo contra la URL publicada | ✅ |

**Credenciales:**
- **AWS por OIDC**: el rol `github-actions-mlops` solo acepta tokens de las ramas `master` y
  `develop` de este repositorio. Sus permisos se limitan al bucket y a los recursos
  `bank-attrition-*`. No hay claves de AWS guardadas en ningún lado.
- **Databricks**: GitHub Secrets.
- Detalle de IAM en [`infra/aws/`](../infra/aws/README.md).

## 3. Disparadores

| Evento | Qué se ejecuta |
|---|---|
| Pull Request a `develop` o `master` | CI (lint + pruebas) |
| Ejecución manual de `train.yml` o push a `develop` con cambios de código | Entrenamiento y registro del modelo |
| Merge a `master` | CD: despliegue de batch y API en AWS |
| Schedule mensual (EventBridge Scheduler, día 1 a las 06:00 Lima) | Lambda batch: features OOT + scoring + reporte de drift |
| Llamada del sistema del asesor | `POST /predict` en el endpoint online |

## 4. Flujo de un modelo de punta a punta

1. Data Engineering publica una nueva entrega → se sube a `raw/<yyyymm>/` y se actualiza el manifiesto.
2. Se generan las features con su linaje.
3. `train.yml` entrena los 3 modelos y registra el mejor en MLflow.
4. Si pasa la validación y supera al actual, recibe el alias `champion`.
5. El batch mensual carga el nuevo `@champion` en su siguiente ejecución, sin cambiar código. La
   API lo toma cuando la Lambda arranca un contenedor nuevo, o de inmediato con un despliegue (`cd.yml`).
6. El batch calcula el PSI; si hay drift crítico, se revisa el modelo y se reentrena.
