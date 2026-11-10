# Ejemplos sintéticos de contrato

`request.json` y `response.json` son **ilustraciones de diseño**, no una solicitud
ya compatible con un modelo entrenado ni el resultado de una inferencia real.
La plantilla no incluye un servicio de predicción implementado.

- El equipo debe adaptar nombres, tipos, campos obligatorios y validaciones a su modelo y signature.
- `metadata` identifica la solicitud; `ID_CORRELATIVO` y `CODMES` no se pasan al vector de predictores.
- Las features son inventadas para ilustrar la estructura. `N_REQUERIMIENTOS_VENTANA` exige definir y verificar la ventana y la agregación antes de usarla.
- Las unidades y rangos de `EDAD` y `ANTIGUEDAD` deben verificarse contra el diccionario oficial.
- El score `0.27` es un valor ficticio; no demuestra desempeño, calibración ni un horizonte de seis meses.
- `model_version` y `prediction_timestamp` son `null` porque aquí no hubo modelo ni ejecución. En respuestas reales, registrar sus valores concretos.
- `example_only` distingue esta muestra de una respuesta real y puede sustituirse al definir el contrato final.

Documentar también una solicitud inválida y su error esperado. Crear ejemplos
sin datos reales y comprobar que API y batch usan el mismo artefacto y producen
scores consistentes para entradas equivalentes.
