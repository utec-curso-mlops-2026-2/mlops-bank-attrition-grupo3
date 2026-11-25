import numpy as np
from fastapi.testclient import TestClient

from bank_attrition import api


class ModeloFalso:
    def __init__(self):
        self.columnas = None

    def predict(self, X):
        self.columnas = list(X.columns)
        return np.array([[0.3, 0.7]])


def _cliente():
    c = {f: 1.0 for f in api.REQUIRED_FIELDS}
    for f in api.CAT_FIELDS:
        c[f] = "X"
    return c


def _client():
    api.app.state.model = ModeloFalso()
    api.app.state.model_version = "1"
    api.app.state.model_name = "test"
    return TestClient(api.app)  # sin "with": no carga el modelo real

def test_predict_ok_con_requerimientos_y_nulos():
    cliente = _cliente()
    cliente["EDAD"] = None
    body = {
        "id_cliente": 1,
        "cliente": cliente,
        "requerimientos": [
            {
                "TIPO_REQUERIMIENTO2": "Reclamo",
                "DICTAMEN": None,
                "CODMES": 202408,
                "PRODUCTO_SERVICIO_2": "Producto 20",
                "SUBMOTIVO_2": "Submotivo 125",
            }
        ],
    }
    r = _client().post("/predict", json=body)
    assert r.status_code == 200
    assert r.json()["prob_fuga"] == 0.7
    assert r.json()["model_version"] == "1"
    cols = api.app.state.model.columnas
    assert "REQ_TOTAL" in cols and "ID_CORRELATIVO" not in cols

def test_features_sin_requerimientos_son_float():
    req = api.PredictRequest(id_cliente=1, cliente=_cliente(), requerimientos=[])
    X = api.to_features(req)
    no_cat = [c for c in X.columns if c not in api.CAT_FIELDS]
    assert all(str(X[c].dtype) == "float64" for c in no_cat)

def test_predict_campo_faltante_devuelve_422():
    cliente = _cliente()
    del cliente["EDAD"]
    r = _client().post("/predict", json={"id_cliente": 1, "cliente": cliente})
    assert r.status_code == 422
    assert "falta el campo 'EDAD'" in r.json()["detail"]


def test_predict_tipo_invalido_devuelve_422():
    cliente = _cliente()
    cliente["EDAD"] = "treinta"
    r = _client().post("/predict", json={"id_cliente": 1, "cliente": cliente})
    assert r.status_code == 422
