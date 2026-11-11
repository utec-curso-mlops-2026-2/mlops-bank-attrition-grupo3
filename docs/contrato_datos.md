# Contrato de datos

## Fuentes
Kaggle: jhonyjacobi/bank-attrition-detection. Versión 202611 (ver manifiesto_datos.json).
Ubicación actual: local `data/raw/202611/` (pendiente migración a S3).

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
