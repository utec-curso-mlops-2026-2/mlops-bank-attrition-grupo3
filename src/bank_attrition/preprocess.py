"""Preprocesamiento: se ajusta solo con train y viaja dentro del modelo."""

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def split_columns(df: pd.DataFrame, id_col: str, target_col: str) -> tuple[list, list]:
    """Devuelve (numéricas, categóricas) excluyendo id y target."""
    feats = df.drop(columns=[c for c in (id_col, target_col) if c in df.columns])
    cat_cols = feats.select_dtypes(exclude="number").columns.tolist()
    num_cols = feats.select_dtypes(include="number").columns.tolist()
    return num_cols, cat_cols


def build_preprocessor(num_cols: list, cat_cols: list) -> ColumnTransformer:
    num = Pipeline(
        [("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]
    )
    cat = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="constant", fill_value="MISSING")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer([("num", num, num_cols), ("cat", cat, cat_cols)])
