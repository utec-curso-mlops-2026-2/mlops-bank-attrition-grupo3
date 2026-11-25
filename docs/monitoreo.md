# Plan de monitoreo del modelo

Este documento describe cómo se vigila el modelo de fuga de clientes en producción. Cubre dos frentes:

- **Data drift**, que ya está implementado y corre en cada ejecución del batch.
- **Model drift y concept drift**, para cuando lleguen las etiquetas reales.

## 1. Punto de partida (línea base)

El modelo `champion` actual es LightGBM, versión 2 en el Model Registry. Sus métricas en el conjunto de test (30 % de train, estratificado) son:

| Métrica | Valor en test | Uso |
|---|---|---|
| AUC | 0.836 | Capacidad de ordenar clientes por riesgo |
| Gini | 0.673 | Equivalente a 2·AUC − 1, estándar en banca |
| KS | 0.513 | Separación máxima entre fugados y no fugados |
| % de fugas capturadas en el top 10 % | 40.1 % (lift 4.0) | **Métrica de negocio principal**: el área de retención contacta primero al decil de mayor riesgo |
| % de fugas capturadas en el top 20 % | 59.9 % (lift 3.0) | Capacidad de campaña ampliada |

Estas cifras son la referencia contra la que se compara el modelo cada mes.

La AUC en train (0.925) es bastante mayor que en test (0.836). Esa diferencia indica algo de sobreajuste, y es una razón más para vigilar el desempeño real.

## 2. Data drift: implementado

Cada ejecución del batch mensual (Lambda `bank-attrition-batch`, lanzada por EventBridge Scheduler el día 1 de cada mes) calcula lo siguiente:

- **PSI por variable** entre la población de entrenamiento y la de aplicación, con 10 bins.
- **PSI sobre la distribución del score**.
- Un **semáforo** por variable y para el score, según el PSI:

  | PSI | Estado |
  |---|---|
  | < 0.10 | Estable |
  | 0.10 – 0.25 | Alerta |
  | > 0.25 | Crítico |

- Dónde queda el resultado:
  - El reporte completo, en `s3://<bucket>/monitoring/<codmes>/psi_variables.csv`.
  - En MLflow, las métricas `psi_score`, `n_vars_alerta` y `n_vars_critico`, junto con el tag `estado_score`.

**Último resultado** (ejecución automática del 25/11/2026, OOT 202408): PSI del score de 0.0008 (estable), sin variables en alerta ni críticas.

El data drift solo indica que **la población cambió**. No dice si el modelo **sigue acertando**. Para eso hacen falta las etiquetas.

## 3. Model drift y concept drift: plan

### 3.1 Cuándo hay etiquetas

El modelo predice la fuga en los **próximos 6 meses**. La etiqueta real de los clientes scoreados en el mes *M* recién se conoce en el mes *M + 6*. Por ejemplo, los clientes scoreados en 202408 tienen etiqueta en 202502.

Por eso el monitoreo de desempeño trabaja siempre con un **rezago de 6 meses**. Cada mes se evalúa la cohorte scoreada 6 meses antes.

### 3.2 Métricas y frecuencia

| Qué se mide | Cómo | Frecuencia |
|---|---|---|
| **Desempeño (model drift)** | AUC, KS y % de fugas capturadas en el top 10 % de la cohorte *M − 6*, comparando sus scores guardados en `scores/<codmes>/` con las fugas reales | Mensual, cuando se cierra la etiqueta |
| **Calibración** | Probabilidad media predicha vs. tasa de fuga observada, global y por decil | Mensual |
| **Concept drift** | Cambio en la tasa de fuga observada y en la relación entre variables y fuga: se compara la importancia de variables de un modelo reentrenado con datos recientes contra la del `champion` | Trimestral |
| **Señales tempranas** (mientras no hay etiquetas) | PSI de variables y del score (ya implementado); % de clientes en segmento de riesgo alto; resultados de las campañas de retención que reporte el negocio | Mensual, en cada batch |

Los resultados se registran como un run `monitoreo_<codmes>` en el mismo experimento de MLflow, para ver su evolución en el tiempo.

### 3.3 Criterios para reentrenar

Se dispara un reentrenamiento si se cumple **cualquiera** de estas condiciones:

| Condición | Umbral |
|---|---|
| Caída de desempeño | AUC de la cohorte < 0.786 (línea base − 0.05) **o** AUC < 0.70 (mínimo de validación) |
| Caída en la métrica de negocio | Captura en el top 10 % < 32 % (80 % de la línea base de 40.1 %) |
| Descalibración | Diferencia > 30 % entre la probabilidad media predicha y la tasa real |
| Data drift sostenido | PSI del score > 0.25 (crítico) **o** más de 3 variables en estado crítico durante 2 meses seguidos |
| Mantenimiento preventivo | Cada 12 meses, aunque no se cumpla nada de lo anterior |

### 3.4 Procedimiento de reentrenamiento

1. Se suben los datos nuevos a `raw/<yyyymm>/` y se actualiza el manifiesto y `config.yaml`.
2. Se ejecuta el workflow `train.yml` (GitHub Actions). Entrena los 3 modelos y registra el mejor.
3. **Champion/challenger:** el nuevo modelo solo pasa a `champion` si supera la AUC mínima (0.70) **y** la AUC del `champion` actual. Si no, queda como `challenger`.
4. Antes de promover a mano un `challenger`, se comparan ambos sobre la cohorte etiquetada más reciente. Esto evita elegir con un test desactualizado.
5. Al integrar a `master`, `cd.yml` despliega la API con el nuevo `champion`. El batch lo toma en su siguiente ejecución.
6. **Rollback:** si el nuevo modelo empeora, se reasigna el alias `champion` a la versión anterior en el Registry.

## 4. Responsables

| Rol | Responsabilidad |
|---|---|
| Equipo MLOps | Revisar cada mes el reporte de PSI y el run de MLflow, y lanzar el reentrenamiento cuando se cumpla un criterio |
| Equipo de Analytics | Proveer las etiquetas reales a los 6 meses y validar la calibración |
| Área de retención | Reportar resultados de campañas como señal temprana |

## 5. Mejoras futuras

- **Alertas automáticas:** una alarma de CloudWatch + SNS que envíe un correo si el batch falla o si el PSI del score supera 0.25.
- **Reentrenamiento automático:** lanzar `train.yml` desde el batch cuando se cumpla un criterio de la sección 3.3, con promoción champion/challenger automática.
- **Dashboard de drift:** evolución mensual del PSI y del desempeño por cohorte.
