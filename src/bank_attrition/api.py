"""Inferencia online: API REST que devuelve la probabilidad de fuga de un cliente."""

import os
from contextlib import asynccontextmanager
from typing import Any

import mlflow
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from mlflow.tracking import MlflowClient
from pydantic import BaseModel, Field

from bank_attrition.features import build_features, load_config

CONFIG_PATH = os.getenv("CONFIG_PATH", "config/config.yaml")
CFG = load_config(CONFIG_PATH)
FCFG = CFG["features"]
REQUIRED_FIELDS = CFG["api"]["base_fields"] + [
    f"{p}_MENOS{i}" for p in FCFG["lag_prefixes"] for i in range(6)
]
CAT_FIELDS = set(CFG["api"]["categorical_fields"])


class Requerimiento(BaseModel):
    TIPO_REQUERIMIENTO2: str
    DICTAMEN: str | None = None
    CODMES: int = Field(ge=190001, le=299912)
    PRODUCTO_SERVICIO_2: str
    SUBMOTIVO_2: str


class PredictRequest(BaseModel):
    id_cliente: int
    codmes_corte: int | None = None
    cliente: dict[str, Any]
    requerimientos: list[Requerimiento] = []


def load_model(app: FastAPI) -> None:
    load_dotenv()
    name = CFG["mlflow"]["model_name"]
    alias = CFG["batch"]["model_alias"]
    app.state.model = mlflow.pyfunc.load_model(f"models:/{name}@{alias}")
    app.state.model_version = (
        MlflowClient().get_model_version_by_alias(name, alias).version
    )
    app.state.model_name = name


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model(app)  # una sola vez al arrancar, no en cada request
    yield


app = FastAPI(title="UTEC Bank - Attrition API", lifespan=lifespan)


def validate_cliente(cliente: dict) -> list[str]:
    errores = [f"falta el campo '{c}'" for c in REQUIRED_FIELDS if c not in cliente]
    for c in REQUIRED_FIELDS:
        v = cliente.get(c)
        if v is None:
            continue
        if c in CAT_FIELDS and not isinstance(v, str):
            errores.append(f"'{c}' debe ser texto")
        elif c not in CAT_FIELDS and (
            isinstance(v, bool) or not isinstance(v, int | float)
        ):
            errores.append(f"'{c}' debe ser numérico")
    return errores


def to_features(req: PredictRequest) -> pd.DataFrame:
    id_col = CFG["data"]["id_col"]
    corte = req.codmes_corte or FCFG["corte"]["oot"]
    cli = pd.DataFrame(
        [
            {
                **{c: req.cliente[c] for c in REQUIRED_FIELDS},
                id_col: req.id_cliente,
                "CODMES": corte,
            }
        ]
    )
    for c in CAT_FIELDS:  # el pipeline trata los nulos como "MISSING"
        cli[c] = cli[c].fillna("MISSING").astype(str)
    req_cols = [
        "TIPO_REQUERIMIENTO2",
        "DICTAMEN",
        "CODMES",
        "PRODUCTO_SERVICIO_2",
        "SUBMOTIVO_2",
    ]
    req_df = pd.DataFrame(
        [r.model_dump() for r in req.requerimientos], columns=req_cols
    )
    req_df[id_col] = req.id_cliente
    X = build_features(cli, req_df, corte, FCFG, id_col).drop(columns=[id_col])
    num = [c for c in X.columns if c not in CAT_FIELDS]
    X[num] = X[num].apply(pd.to_numeric).astype("float64")
    return X


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_name": app.state.model_name,
        "model_version": app.state.model_version,
    }


@app.post("/predict")
def predict(req: PredictRequest):
    errores = validate_cliente(req.cliente)
    if errores:
        raise HTTPException(status_code=422, detail=errores)
    try:
        X = to_features(req)
        proba = app.state.model.predict(X)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"No se pudo scorear: {e}") from e
    proba = proba.iloc[0, 1] if isinstance(proba, pd.DataFrame) else proba[0, 1]
    return {
        "id_cliente": req.id_cliente,
        "prob_fuga": round(float(proba), 6),
        "model_name": app.state.model_name,
        "model_version": app.state.model_version,
    }
