# Decisiones técnicas

Cada decisión indica **qué** se eligió, **por qué**, qué **alternativas** se consideraron y sus
**limitaciones**. Se distingue entre *supuestos* (S) y hechos *comprobados* (C). Las evidencias están
en [`docs/evidencias/`](evidencias/).

## 1. Datos y features

| Decisión | Motivo | Alternativas | Limitaciones |
|---|---|---|---|
| **Corte de train = 202407** (S) | El `CODMES` de clientes train (201208) es inconsistente con los requerimientos (202403–202407); se toma el último mes de requerimientos. | Usar 201208 literal (dejaría la ventana vacía). | Pendiente de confirmación docente. |
| **Ventana de requerimientos de 5 meses** | Train (202403–202407) y OOT (202404–202408) quedan con la misma ventana, así las features son comparables. | Usar todo el histórico disponible (ventanas desiguales entre train y OOT). | Se descartan requerimientos más antiguos. |
| **Top-5 producto/submotivo calculado en train** | Evita *leakage* del OOT y limita la dimensionalidad. | Todas las categorías o *target encoding*. | Categorías nuevas del OOT caen en los conteos genéricos. |
| **Clientes sin requerimientos → conteos = 0 y `FLG_TIENE_REQ = 0`** (C: ≈50 % en train) | La ausencia de reclamos es información, no un dato faltante. | Imputar con la mediana. | — |
| **Variables de rezago `_MENOS0..5`** para saldos, seguros, accesos por canal y entidades | Capturan tendencias de los últimos 6 meses. | Solo el mes actual o promedios. | Aumentan el número de columnas. |

## 2. Versionamiento de datos

| Decisión | Motivo | Alternativas | Limitaciones |
|---|---|---|---|
| **S3 con versionado de objetos + carpeta por fecha de corte** (C, evidencias 19–23) | Requisito R3; permite identificar y recuperar cualquier versión. | DVC. | Depende de mantener el manifiesto actualizado. |
| **Manifiesto con SHA-256 y `VersionId`** (C) | Garantiza que se entrena con exactamente los datos esperados; `features.py` falla si no coinciden. | Confiar solo en la ruta. | Hay que commitear el manifiesto tras cada entrega. |
| **Linaje registrado en cada run de MLflow** (C, evidencias 24 y 26) | Trazabilidad datos → features → modelo → scores. | — | — |
| **Sin Feature Store dedicado** | Las features en `features/<yyyymm>/` se comparten entre entrenamiento y batch; la API usa la misma función `build_features`. | SageMaker Feature Store (opcional en R3). | No hay consulta de features por cliente en línea. |

## 3. Modelado

| Decisión | Motivo | Alternativas | Limitaciones |
|---|---|---|---|
| **Split aleatorio estratificado 70/30, semilla 42** | Un solo periodo etiquetado; la estratificación mantiene la tasa de fuga (15.5 %) en ambos lados. | Split temporal (no hay varios periodos etiquetados). | No mide estabilidad temporal; para eso se usa el PSI sobre el OOT. |
| **Preprocesamiento dentro del `Pipeline` de sklearn** | La imputación se ajusta solo con train y viaja con el modelo: batch y API la aplican idéntica. | Preprocesar por separado y guardar los objetos. | — |
| **Imputación: mediana (numéricas) y `"MISSING"` (categóricas)** | Robusta frente a valores extremos y simple de explicar. | KNN o imputación iterativa. | — |
| **3 modelos: Regresión Logística, Random Forest, LightGBM** | Un baseline interpretable, un ensamble de bagging y uno de boosting. | XGBoost, CatBoost. | Hiperparámetros fijos en `config.yaml` (sin búsqueda). |
| **Desbalance con `class_weight=balanced` / `is_unbalance=true`** | La clase positiva es minoritaria (15.5 %). | SMOTE o submuestreo. | Las probabilidades quedan desplazadas; afecta la lectura absoluta del score, no el ranking. |
| **Selección por AUC en test** | El negocio necesita **ordenar** clientes; el AUC mide calidad de ranking y no depende de un umbral. | KS o captura en top 10 %. | Se reportan igual KS, Gini y captura top 10 %/20 % para el negocio. |
| **Umbral 0.5 solo para la matriz de confusión** | El uso real es por ranking/decil, no por clasificación binaria. | Optimizar el umbral. | — |

## 4. Registro y promoción del modelo

| Decisión | Motivo | Alternativas | Limitaciones |
|---|---|---|---|
| **MLflow en Databricks (tracking + Unity Catalog)** | Tracking server remoto administrado y compartido por el equipo, sin mantener infraestructura. | Servidor MLflow propio en EC2. | Depende de la cuenta de Databricks. |
| **Alias `champion` / `challenger`** | Los stages están deprecados en MLflow; los alias permiten cambiar de modelo sin tocar el código. | Stages `Production`/`Staging`. | — |
| **Validación: AUC test ≥ 0.70** | Mínimo aceptable para priorizar campañas. | Exigir también un KS mínimo. | Un único criterio. |
| **Champion solo si supera al actual** | Evita reemplazar un modelo por uno peor. | Promover siempre el último. | Compara AUC en test de distintos splits si cambian los datos. |
| **Serialización `cloudpickle`** | `skops` exige declarar los tipos confiables del pipeline. | `skops`, `pickle`. | Requiere las mismas versiones de librerías (fijadas en `requirements.txt`). |

## 5. Monitoreo

| Decisión | Motivo | Alternativas | Limitaciones |
|---|---|---|---|
| **PSI por variable y sobre el score, 10 bins** | Métrica estándar en riesgo bancario; umbrales de referencia del curso (0.10 / 0.25). | Kolmogorov-Smirnov, Jensen-Shannon. | Sensible al número de bins. |
| **Reporte en S3 y en MLflow** (C, evidencias 12, 13, 27 y 30) | Consulta por negocio (S3) y trazabilidad técnica (MLflow). | — | — |

## 6. Servicios AWS e inferencia

| Decisión | Motivo | Alternativas | Limitaciones |
|---|---|---|---|
| **API con FastAPI** | Validación con Pydantic y documentación OpenAPI automática (evidencia 15). | Flask. | — |
| **Modelo cargado una vez al arrancar** | Menor latencia por request. | Cargar en cada request. | Para tomar un nuevo `champion` hay que reiniciar el servicio. |
| **Servicio de despliegue batch** 🚧 | `<completar>` | `<completar>` | `<completar>` |
| **Servicio de despliegue online** 🚧 | `<completar>` | `<completar>` | `<completar>` |
