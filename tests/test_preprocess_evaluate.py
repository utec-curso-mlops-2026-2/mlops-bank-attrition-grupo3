import numpy as np
import pandas as pd

from bank_attrition.evaluate import capture_rate, compute_metrics
from bank_attrition.preprocess import build_preprocessor, split_columns


def _df():
    return pd.DataFrame(
        {
            "ID_CORRELATIVO": [1, 2, 3, 4],
            "EDAD": [30.0, np.nan, 50.0, 40.0],
            "RANG_INGRESO": ["R1", None, "R2", "R1"],
            "ATTRITION": [0, 1, 0, 1],
        }
    )


def test_split_columns_excluye_id_y_target():
    num, cat = split_columns(_df(), "ID_CORRELATIVO", "ATTRITION")
    assert num == ["EDAD"]
    assert cat == ["RANG_INGRESO"]


def test_preprocesador_imputa_y_tolera_categorias_nuevas():
    df = _df()
    prep = build_preprocessor(["EDAD"], ["RANG_INGRESO"]).fit(df)
    out = prep.transform(pd.DataFrame({"EDAD": [np.nan], "RANG_INGRESO": ["NUEVA"]}))
    assert not np.isnan(out).any()


def test_capture_rate_top_perfecto():
    y = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    score = [0.9, 0.1, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    assert capture_rate(y, score, 0.1) == 1.0


def test_metricas_gini_coherente_con_auc():
    m = compute_metrics([0, 1, 0, 1], [0.1, 0.9, 0.2, 0.8], "test")
    assert m["test_auc"] == 1.0
    assert m["test_gini"] == 1.0
    assert m["test_ks"] == 1.0
