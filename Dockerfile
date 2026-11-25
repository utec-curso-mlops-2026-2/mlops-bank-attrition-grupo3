# Imagen de inferencia para AWS Lambda (arm64): API online y batch programado.
# El handler se elige en cada función Lambda (ImageConfig.Command).
FROM public.ecr.aws/lambda/python:3.12

ENV HOME=/tmp \
    MPLCONFIGDIR=/tmp/matplotlib \
    GIT_PYTHON_REFRESH=quiet \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt --target ${LAMBDA_TASK_ROOT}
# LightGBM necesita OpenMP (libgomp), que la imagen base de Lambda no incluye.
RUN dnf install -y libgomp && dnf clean all

COPY src/bank_attrition ${LAMBDA_TASK_ROOT}/bank_attrition
COPY config ${LAMBDA_TASK_ROOT}/config
COPY docs/manifiesto_datos.json ${LAMBDA_TASK_ROOT}/docs/manifiesto_datos.json

CMD ["bank_attrition.lambda_handlers.api_handler"]
