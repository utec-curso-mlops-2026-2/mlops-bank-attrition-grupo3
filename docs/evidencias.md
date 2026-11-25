# Evidencias

Este documento relaciona cada criterio de la rúbrica con su evidencia. Hay tres tipos:

- **Capturas** de pantalla, en [`evidencias/`](evidencias/).
- **Salidas de consola** de AWS y GitHub, en [`evidencias/salidas/`](evidencias/salidas/).
- **Enlaces** verificables a PRs y ejecuciones de GitHub Actions.

Las capturas 01–30 corresponden a la cuenta AWS de laboratorio y a la ejecución local. Desde el 25/11/2026 la solución corre en la cuenta AWS del equipo (`484815418393`, `us-east-2`). Las evidencias de esa etapa son las salidas de consola y las capturas desde la 31 en adelante.

Repositorio: <https://github.com/utec-curso-mlops-2026-2/mlops-bank-attrition-grupo3>

## R1. Control de versiones y trabajo colaborativo

| Evidencia | Detalle |
|---|---|
| [01](evidencias/01.%20R1%20-%20Rulesets%20en%20Github.png), [01.1](evidencias/01.1%20R1%20-%20Detalle%20del%20ruleset%20de%20la%20branch%20develop.png), [01.2](evidencias/01.2%20R1%20-%20Detalle%20del%20ruleset%20de%20la%20branch%20master.png) | Rulesets en `develop` y `master`: PR obligatorio, 1 aprobación y CI en verde |
| [02](evidencias/02.%20R1%20-%20Pull%20Requests%20Mergeados%20con%20Revisor%20y%20Aprobador.png) | PRs integrados con revisor y aprobador |
| [03](evidencias/03.%20R1%20-%20Gr%C3%A1fico%20de%20las%20Ramas%20en%20Github.png) | Gitflow: `feature/*` → `develop` → `master` |
| [17](evidencias/17.%20R1%20-%20Para%20que%20se%20ejecute%20un%20Pull%20Request%2C%20hace%20falta%20que%20pase%20el%20CI.png), [18](evidencias/18.%20R1%20-%20Cambios%20revertidos%20para%20que%20pase%20el%20check.png) | Un CI fallido bloquea el PR ([#9](https://github.com/utec-curso-mlops-2026-2/mlops-bank-attrition-grupo3/pull/9), [ejecución fallida](https://github.com/utec-curso-mlops-2026-2/mlops-bank-attrition-grupo3/actions/runs/44231773534)) |
| [Lista de PRs](https://github.com/utec-curso-mlops-2026-2/mlops-bank-attrition-grupo3/pulls?q=is%3Apr) | 18 PRs, cada uno revisado y aprobado por otro integrante |

## R2. Pipeline de entrenamiento

| Evidencia | Detalle |
|---|---|
| [04](evidencias/04.%20R4%20-%20Pipeline%20de%20Train%20con%20los%20tres%20modelos%20entrenados.png) | Run padre con 3 modelos en runs anidados |
| [07](evidencias/07.%20R4%20-%20Comparaci%C3%B3n%20de%20los%20modelos%20entrenados.png) | Comparación de modelos y selección por `test_auc` |
| [salidas/R6_train_workflow.txt](evidencias/salidas/R6_train_workflow.txt) | Entrenamiento en GitHub Actions: logreg 0.790, random forest 0.800, **LightGBM 0.836** (elegido) |

## R3. Datos versionados en S3

| Evidencia | Detalle |
|---|---|
| [19](evidencias/19.%20R3%20-%20Estructura%20del%20bucket%20S3%20%28raw%20y%20features%29.png)–[23](evidencias/23.%20R3%20-%20Bloqueo%20de%20acceso%20p%C3%BAblico%20del%20bucket.png) | Estructura `raw/` y `features/`, versionado activo y bloqueo de acceso público |
| [24](evidencias/24.%20R3%20-%20Linaje%20de%20datos%20en%20el%20run%20de%20entrenamiento.png), [25](evidencias/25.%20R3%20-%20M%C3%A9tricas%20del%20entrenamiento%20con%20datos%20de%20S3.png) | Linaje de datos (URI, VersionId, SHA-256) en el run de MLflow |
| [manifiesto_datos.json](manifiesto_datos.json) | VersionId y SHA-256 de cada archivo crudo en el bucket actual |
| Artefacto `linaje-datos-*` de [train.yml](https://github.com/utec-curso-mlops-2026-2/mlops-bank-attrition-grupo3/actions/runs/45527607101) | Linaje crudos → features generado en CI |

## R4. Tracking con MLflow

| Evidencia | Detalle |
|---|---|
| [04](evidencias/04.%20R4%20-%20Pipeline%20de%20Train%20con%20los%20tres%20modelos%20entrenados.png)–[07](evidencias/07.%20R4%20-%20Comparaci%C3%B3n%20de%20los%20modelos%20entrenados.png) | Tracking server en Databricks, métricas, tags y artefactos (ROC, matriz de confusión, importancia) |

## R5. Model Registry

| Evidencia | Detalle |
|---|---|
| [08](evidencias/08.%20R5%20-%20Versionamiento%20del%20modelo.png) | Versiones del modelo y aliases |
| [09](evidencias/09.%20R5%20-%20Signature%20de%20los%20datos%20de%20entrada.png), [10](evidencias/10.%20R5%20-%20Input%20Example%20para%20el%20modelo.png) | Signature e input example |
| [salidas/R6_train_workflow.txt](evidencias/salidas/R6_train_workflow.txt) | Validación champion/challenger: la v4 no supera al champion v2 y queda como `challenger` |

## R6. CI/CD con GitHub Actions

| Evidencia | Detalle |
|---|---|
| [17](evidencias/17.%20R1%20-%20Para%20que%20se%20ejecute%20un%20Pull%20Request%2C%20hace%20falta%20que%20pase%20el%20CI.png) | **CI** en cada PR; si falla, bloquea el merge |
| [Ejecución 45527607101](https://github.com/utec-curso-mlops-2026-2/mlops-bank-attrition-grupo3/actions/runs/45527607101), [45529104899](https://github.com/utec-curso-mlops-2026-2/mlops-bank-attrition-grupo3/actions/runs/45529104899) · [salida](evidencias/salidas/R6_train_workflow.txt) | **Entrenamiento** (`train.yml`), disparado por push a `develop`. Tres jobs encadenados, con artefacto de linaje y outputs entre jobs |
| [salidas/R6_credenciales_oidc.txt](evidencias/salidas/R6_credenciales_oidc.txt) | Credenciales: AWS por OIDC (sin claves) y Databricks en GitHub Secrets |
| [salidas/R6_R8_recursos_aws.txt](evidencias/salidas/R6_R8_recursos_aws.txt) | Imagen en ECR y Lambdas desplegadas |
| [31](evidencias/31.%20R6%20-%20Workflow%20de%20entrenamiento%20en%20GitHub%20Actions.png) | `train.yml` disparado por push a `develop`: 3 jobs en verde y resumen (LightGBM, AUC 0.8363, v4 `challenger`) |
| 32 *(pendiente)* | Captura de la ejecución de **CD** (`cd.yml`) al integrar a `master`, con la prueba de humo |

## R7. Inferencia batch en AWS con scheduling

| Evidencia | Detalle |
|---|---|
| [11](evidencias/11.%20R7%20-%20Resultado%20de%20la%20ejecuci%C3%B3n%20en%20batch.png), [11.1](evidencias/11.1%20R7%20-%20Scores%20obtenidos%20en%20el%20batch.png), [26](evidencias/26.%20R7%20-%20Run%20batch%20con%20linaje%20de%20datos.png)–[29](evidencias/29.%20R7%20-%20Scores%20versionados%20en%20S3.png) | Batch con el modelo del Registry y scores en S3 (etapa local) |
| [salidas/R7_schedule_eventbridge.txt](evidencias/salidas/R7_schedule_eventbridge.txt) | Schedule `bank-attrition-batch-mensual`: `cron(0 6 1 * ? *)` en America/Lima |
| [salidas/R7_cloudwatch_batch.txt](evidencias/salidas/R7_cloudwatch_batch.txt) | **Ejecución automática** lanzada por EventBridge Scheduler el 2026-11-25 a las 01:42 UTC: 14 000 clientes scoreados en 14.5 s, logs en CloudWatch |
| [salidas/R7_R9_salidas_s3.txt](evidencias/salidas/R7_R9_salidas_s3.txt) | `scores.csv` versionado en S3 con id, probabilidad, decil, segmento, fecha y versión del modelo |
| [33](evidencias/33.%20R7%20-%20Schedule%20mensual%20en%20EventBridge.png) | Schedule `bank-attrition-batch-mensual` habilitado, con destino la Lambda `bank-attrition-batch` |
| [34](evidencias/34.%20R7%20-%20Logs%20del%20batch%20en%20CloudWatch.png) | Log group `/aws/lambda/bank-attrition-batch` con el stream de la ejecución automática (contenido en [R7_cloudwatch_batch.txt](evidencias/salidas/R7_cloudwatch_batch.txt)) |

## R8. Inferencia online en AWS

| Evidencia | Detalle |
|---|---|
| [14](evidencias/14.%20R8%20-%20Ejecuci%C3%B3n%20exitosa%20con%20API%20Local.png)–[16](evidencias/16.%20R8%20-%20Ejecuci%C3%B3n%20fallida%20adrede.png) | API local, OpenAPI y error de validación |
| [salidas/R8_api_aws.txt](evidencias/salidas/R8_api_aws.txt) | **API en AWS** (Lambda + Function URL): `/health` 200, `/predict` 200 con `prob_fuga=0.639375`, entrada inválida 422 |
| [README §6](../README.md#6-cómo-invocar-el-endpoint) | Ejemplo de request y response con la URL pública |
| [35](evidencias/35.%20R8%20-%20Lambda%20de%20la%20API%20con%20Function%20URL.png) | Lambda `bank-attrition-api`: imagen arm64 desde ECR y Function URL pública |

## R9. Monitoreo

| Evidencia | Detalle |
|---|---|
| [12](evidencias/12.%20R9%20-%20Ejecuci%C3%B3n%20en%20Batch%20con%20psi_score%2C%20cantidad%20de%20variables%20en%20alerta%20y%20cr%C3%ADticas.png), [13](evidencias/13.%20R9%20-%20Artefacto%20con%20el%20score%20psi%20de%20las%20variables.png), [30](evidencias/30.%20R9%20-%20Reporte%20PSI%20versionado%20en%20S3.png) | PSI por variable y del score en MLflow y S3 |
| [salidas/R7_R9_salidas_s3.txt](evidencias/salidas/R7_R9_salidas_s3.txt) | Reporte PSI de la ejecución automática: score 0.0008 (estable), 0 variables en alerta |
| [monitoreo.md](monitoreo.md) *(pendiente)* | Plan de model/concept drift |

## R10. Arquitectura y documentación

| Evidencia | Detalle |
|---|---|
| [README](../README.md), [arquitectura.md](arquitectura.md) | Diagrama, componentes, disparadores y cómo ejecutar |
| [decisiones.md](decisiones.md), [despliegue.md](despliegue.md), [infra/aws/](../infra/aws/README.md) | Decisiones justificadas, operación, permisos, costos y cómo recrear la infraestructura |

## Pendientes

- Ejecución de `cd.yml` al integrar a `master`.
- `monitoreo.md`.
- Informe técnico en PDF.
