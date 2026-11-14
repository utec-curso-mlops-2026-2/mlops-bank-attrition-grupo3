"""Métricas de negocio y gráficos de evaluación."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    ConfusionMatrixDisplay,
    RocCurveDisplay,
    roc_auc_score,
    roc_curve,
)


def ks_statistic(y_true, y_score) -> float:
    fpr, tpr, _ = roc_curve(y_true, y_score)
    return float(np.max(tpr - fpr))


def capture_rate(y_true, y_score, top_frac: float) -> float:
    """% de fugas reales capturadas en el top_frac de clientes con mayor score."""
    y_true = np.asarray(y_true)
    n_top = int(np.ceil(len(y_true) * top_frac))
    top_idx = np.argsort(-np.asarray(y_score))[:n_top]
    return float(y_true[top_idx].sum() / y_true.sum())


def compute_metrics(y_true, y_score, prefix: str) -> dict:
    auc = roc_auc_score(y_true, y_score)
    m = {"auc": auc, "gini": 2 * auc - 1, "ks": ks_statistic(y_true, y_score)}
    for frac in (0.1, 0.2):
        cap = capture_rate(y_true, y_score, frac)
        pct = int(frac * 100)
        m[f"capture_top{pct}"] = cap
        m[f"lift_top{pct}"] = cap / frac
    return {f"{prefix}_{k}": float(v) for k, v in m.items()}


def plot_roc(y_true, y_score):
    fig, ax = plt.subplots(figsize=(5, 5))
    RocCurveDisplay.from_predictions(y_true, y_score, ax=ax)
    ax.set_title("Curva ROC (test)")
    return fig


def plot_confusion(y_true, y_score, threshold: float):
    fig, ax = plt.subplots(figsize=(5, 5))
    y_pred = (np.asarray(y_score) >= threshold).astype(int)
    ConfusionMatrixDisplay.from_predictions(y_true, y_pred, ax=ax)
    ax.set_title(f"Matriz de confusión (umbral {threshold})")
    return fig


def feature_importance(pipeline, top_n: int = 20) -> pd.Series:
    names = pipeline.named_steps["prep"].get_feature_names_out()
    model = pipeline.named_steps["model"]
    if hasattr(model, "feature_importances_"):
        imp = model.feature_importances_
    else:
        imp = np.abs(model.coef_[0])
    return pd.Series(imp, index=names).sort_values(ascending=False).head(top_n)


def plot_importance(imp: pd.Series):
    fig, ax = plt.subplots(figsize=(7, 6))
    imp[::-1].plot.barh(ax=ax)
    ax.set_title("Importancia de variables (top 20)")
    fig.tight_layout()
    return fig
