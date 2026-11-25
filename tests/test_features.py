import pandas as pd

from bank_attrition.features import _meses_entre, build_req_features


def _req():
    return pd.DataFrame(
        {
            "ID_CORRELATIVO": [1, 1, 1, 2],
            "TIPO_REQUERIMIENTO2": ["Reclamo", "Solicitud", "Reclamo", "Reclamo"],
            "DICTAMEN": ["NO PROCEDE", None, "PROCEDE TOTAL", "NO PROCEDE"],
            "CODMES": [202407, 202405, 202402, 202403],
            "PRODUCTO_SERVICIO_2": [
                "Producto 20",
                "Producto 99",
                "Producto 20",
                "Producto 07",
            ],
            "SUBMOTIVO_2": [
                "Submotivo 125",
                "Submotivo 1",
                "Submotivo 125",
                "Submotivo 88",
            ],
        }
    )


def test_meses_entre_cruza_anio():
    assert _meses_entre(pd.Series([202312]), 202401).iloc[0] == 1


def test_ventana_excluye_meses_fuera_de_rango():
    f = build_req_features(
        _req(),
        202407,
        5,
        ["Producto 20"],
        ["Submotivo 125"],
        ["Reclamo", "Solicitud"],
        ["PROCEDE TOTAL", "NO PROCEDE", "PROCEDE PARCIAL", "SIN_DICTAMEN"],
    )
    assert f.loc[1, "REQ_DICT_PROCEDE_PARCIAL"] == 0  # categoría ausente igual genera columna
    assert f.loc[1, "REQ_TOTAL"] == 2  # 202402 queda fuera de la ventana
    assert f.loc[1, "REQ_ULT_MES"] == 1
    assert f.loc[1, "REQ_DICT_SIN_DICTAMEN"] == 1
    assert f.loc[1, "REQ_PROD_OTROS"] == 1
    assert f.loc[2, "REQ_MESES_DESDE_ULT"] == 4
