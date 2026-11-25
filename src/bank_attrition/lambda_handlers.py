"""Puntos de entrada para AWS Lambda: API online (R8) y batch programado (R7).

La misma imagen sirve para ambas funciones; cada una elige su handler en ImageConfig.Command:
- bank_attrition.lambda_handlers.api_handler: FastAPI detrás de una Function URL.
- bank_attrition.lambda_handlers.batch_handler: invocado por EventBridge Scheduler.
"""

import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CONFIG_PATH = os.getenv("CONFIG_PATH", "config/config.yaml")

_api_handler = None


def api_handler(event, context):
    """Adapta los eventos HTTP de la Function URL a la app FastAPI."""
    global _api_handler
    if _api_handler is None:
        from mangum import Mangum

        from bank_attrition import api

        # Cargar el modelo una sola vez por contenedor (cold start), no en cada request.
        # Mangum no ejecuta el lifespan de FastAPI de forma persistente.
        api.load_model(api.app)
        _api_handler = Mangum(api.app, lifespan="off")
    return _api_handler(event, context)


def batch_handler(event, context):
    """Recalcula las features de aplicación (OOT) desde S3 y ejecuta el scoring batch."""
    from bank_attrition import batch, features

    logger.info("Evento: %s", json.dumps(event, default=str))
    features_uri = features.run("oot", CONFIG_PATH)
    batch.run(CONFIG_PATH)
    return {"status": "ok", "features": features_uri}
