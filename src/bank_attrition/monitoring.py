"""Data drift: PSI por variable y sobre el score, con semáforo."""

import numpy as np
import pandas as pd

EPS = 1e-6


def psi_numeric(expected, actual, bins: int = 10) -> float:
    """PSI con cortes por cuantiles de la población de referencia (expected)."""
    expected = pd.Series(expected).dropna().to_numpy(dtype=float)
    actual = pd.Series(actual).dropna().to_numpy(dtype=float)
    cuts = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(cuts) < 2:  # variable constante en la referencia
        return 0.0
    cuts[0], cuts[-1] = -np.inf, np.inf
    e = np.histogram(expected, cuts)[0] / len(expected) + EPS
    a = np.histogram(actual, cuts)[0] / len(actual) + EPS
    return float(np.sum((a - e) * np.log(a / e)))


def psi_categorical(expected, actual) -> float:
    e = pd.Series(expected).fillna("MISSING").value_counts(normalize=True)
    a = pd.Series(actual).fillna("MISSING").value_counts(normalize=True)
    cats = e.index.union(a.index)
    e, a = e.reindex(cats, fill_value=0) + EPS, a.reindex(cats, fill_value=0) + EPS
    return float(np.sum((a - e) * np.log(a / e)))


def semaforo(psi: float, alerta: float = 0.10, critico: float = 0.25) -> str:
    if psi < alerta:
        return "estable"
    return "alerta" if psi < critico else "critico"


def drift_report(
    ref: pd.DataFrame,
    cur: pd.DataFrame,
    cols: list,
    bins: int = 10,
    alerta: float = 0.10,
    critico: float = 0.25,
) -> pd.DataFrame:
    filas = []
    for c in cols:
        if pd.api.types.is_numeric_dtype(ref[c]):
            psi = psi_numeric(ref[c], cur[c], bins)
        else:
            psi = psi_categorical(ref[c], cur[c])
        filas.append(
            {"variable": c, "psi": psi, "estado": semaforo(psi, alerta, critico)}
        )
    return pd.DataFrame(filas).sort_values("psi", ascending=False, ignore_index=True)
