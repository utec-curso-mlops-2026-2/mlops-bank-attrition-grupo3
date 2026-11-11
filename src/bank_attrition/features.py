"""Cruce clientes + requerimientos y construcción de features (1 fila por cliente)."""

import argparse
import re
from pathlib import Path

import pandas as pd
import yaml


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _slug(valor: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(valor).upper()).strip("_")


def _meses_entre(codmes_inicio: pd.Series, codmes_fin: int) -> pd.Series:
    """Meses transcurridos entre cada CODMES (yyyymm) y codmes_fin."""
    anio_fin, mes_fin = divmod(codmes_fin, 100)
    anio, mes = codmes_inicio // 100, codmes_inicio % 100
    return (anio_fin - anio) * 12 + (mes_fin - mes)


def build_req_features(
    req: pd.DataFrame,
    codmes_corte: int,
    n_meses: int,
    top_productos: list,
    top_submotivos: list,
    tipos: list,
    dictamenes: list,
    id_col: str = "ID_CORRELATIVO",
) -> pd.DataFrame:
    req = req.copy()
    req["DICTAMEN"] = req["DICTAMEN"].fillna("SIN_DICTAMEN")
    req["MESES_ATRAS"] = _meses_entre(req["CODMES"], codmes_corte)
    req = req[(req["MESES_ATRAS"] >= 0) & (req["MESES_ATRAS"] < n_meses)]

    req["PROD"] = req["PRODUCTO_SERVICIO_2"].where(
        req["PRODUCTO_SERVICIO_2"].isin(top_productos), "OTROS"
    )
    req["SUBM"] = req["SUBMOTIVO_2"].where(req["SUBMOTIVO_2"].isin(top_submotivos), "OTROS")
    req["TIPO_DICT"] = req["TIPO_REQUERIMIENTO2"] + "_" + req["DICTAMEN"]

    # Categorías fijas: train y OOT generan las mismas columnas aunque falte un valor
    categorias = {
        "TIPO_REQUERIMIENTO2": tipos,
        "DICTAMEN": dictamenes,
        "TIPO_DICT": [f"{t}_{d}" for t in tipos for d in dictamenes],
        "PROD": list(top_productos) + ["OTROS"],
        "SUBM": list(top_submotivos) + ["OTROS"],
    }

    g = req.groupby(id_col)
    partes = [
        g.size().rename("REQ_TOTAL"),
        g["MESES_ATRAS"].min().rename("REQ_MESES_DESDE_ULT"),
        req[req["MESES_ATRAS"] == 0].groupby(id_col).size().rename("REQ_ULT_MES"),
    ]
    for col, prefijo in [
        ("TIPO_REQUERIMIENTO2", "REQ_TIPO"),
        ("DICTAMEN", "REQ_DICT"),
        ("TIPO_DICT", "REQ_TIPODICT"),
        ("PROD", "REQ_PROD"),
        ("SUBM", "REQ_SUBM"),
    ]:
        conteo = pd.crosstab(req[id_col], req[col]).reindex(columns=categorias[col], fill_value=0)
        conteo.columns = [f"{prefijo}_{_slug(c)}" for c in conteo.columns]
        partes.append(conteo)
    return pd.concat(partes, axis=1)


def build_lag_features(cli: pd.DataFrame, lag_prefixes: list, n_lags: int = 6) -> pd.DataFrame:
    nuevas = {}
    for p in lag_prefixes:
        cols = [f"{p}_MENOS{i}" for i in range(n_lags)]
        nuevas[f"{p}_MEAN"] = cli[cols].mean(axis=1)
        nuevas[f"{p}_MAX"] = cli[cols].max(axis=1)
        nuevas[f"{p}_TREND"] = cli[f"{p}_MENOS0"] - cli[f"{p}_MENOS{n_lags - 1}"]
    return pd.concat([cli, pd.DataFrame(nuevas, index=cli.index)], axis=1)


def build_features(
    cli: pd.DataFrame,
    req: pd.DataFrame,
    codmes_corte: int,
    fcfg: dict,
    id_col: str = "ID_CORRELATIVO",
) -> pd.DataFrame:
    req_feats = build_req_features(
        req,
        codmes_corte,
        fcfg["n_meses_req"],
        fcfg["top_productos"],
        fcfg["top_submotivos"],
        fcfg["tipos_req"],
        fcfg["dictamenes"],
        id_col,
    )
    df = build_lag_features(cli, fcfg["lag_prefixes"]).drop(columns=["CODMES"])
    df = df.merge(req_feats, left_on=id_col, right_index=True, how="left")
    req_cols = [c for c in df.columns if c.startswith("REQ_")]
    df["FLG_TIENE_REQ"] = df["REQ_TOTAL"].notna().astype(int)
    df["REQ_MESES_DESDE_ULT"] = df["REQ_MESES_DESDE_ULT"].fillna(fcfg["n_meses_req"])
    df[req_cols] = df[req_cols].fillna(0)
    return df


def run(split: str, config_path: str = "config/config.yaml") -> Path:
    cfg = load_config(config_path)
    d, fcfg = cfg["data"], cfg["features"]
    raw = Path(d["raw_path"])
    cli = pd.read_csv(raw / d[f"clientes_{split}"])
    req = pd.read_csv(raw / d[f"req_{split}"])
    df = build_features(cli, req, fcfg["corte"][split], fcfg, d["id_col"])
    out = Path(fcfg["output_path"]) / f"{split}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"{split}: {df.shape} -> {out}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["train", "oot"], required=True)
    ap.add_argument("--config", default="config/config.yaml")
    a = ap.parse_args()
    run(a.split, a.config)
