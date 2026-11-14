"""Pipeline de entrenamiento: split, 3 modelos, selección, registro y validación."""

import argparse
import getpass
import os
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import mlflow
import pandas as pd
from dotenv import load_dotenv
from lightgbm import LGBMClassifier
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from bank_attrition.evaluate import (
    compute_metrics,
    feature_importance,
    plot_confusion,
    plot_importance,
    plot_roc,
)
from bank_attrition.features import load_config
from bank_attrition.preprocess import build_preprocessor, split_columns

MODELS = {
    "logreg": LogisticRegression,
    "random_forest": RandomForestClassifier,
    "lightgbm": LGBMClassifier,
}


def git_commit() -> str:
    if os.getenv("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        )
        return out.stdout.strip() or "unknown"
    except FileNotFoundError:
        return "unknown"


def train_one(name, params, X_tr, y_tr, X_te, y_te, num_cols, cat_cols, threshold):
    """Entrena un modelo en un run anidado y devuelve (pipeline, métricas)."""
    pipe = Pipeline(
        [
            ("prep", build_preprocessor(num_cols, cat_cols)),
            ("model", MODELS[name](**params)),
        ]
    )
    with mlflow.start_run(run_name=name, nested=True):
        pipe.fit(X_tr, y_tr)
        s_tr = pipe.predict_proba(X_tr)[:, 1]
        s_te = pipe.predict_proba(X_te)[:, 1]
        metrics = {
            **compute_metrics(y_tr, s_tr, "train"),
            **compute_metrics(y_te, s_te, "test"),
        }
        mlflow.log_param("model_type", name)  # hiperparámetros: los registra autolog
        mlflow.log_metrics(metrics)
        imp = feature_importance(pipe)
        for fname, fig in [
            ("roc_curve.png", plot_roc(y_te, s_te)),
            ("confusion_matrix.png", plot_confusion(y_te, s_te, threshold)),
            ("feature_importance.png", plot_importance(imp)),
        ]:
            mlflow.log_figure(fig, fname)
            plt.close(fig)
    return pipe, metrics


def promote(client, model_name, version, test_auc, min_auc) -> str:
    """Valida y asigna alias: champion si supera al actual, challenger si no."""
    if test_auc < min_auc:
        client.set_model_version_tag(model_name, version, "validation", "rejected")
        return "rejected"
    client.set_model_version_tag(model_name, version, "validation", "passed")
    try:
        champ = client.get_model_version_by_alias(model_name, "champion")
        champ_auc = client.get_run(champ.run_id).data.metrics.get("test_auc", 0)
    except Exception:  # no existe champion todavía
        champ_auc = -1
    alias = "champion" if test_auc > champ_auc else "challenger"
    client.set_registered_model_alias(model_name, alias, version)
    return alias


def run(config_path: str = "config/config.yaml") -> None:
    load_dotenv()
    cfg = load_config(config_path)
    d, tcfg, mcfg = cfg["data"], cfg["train"], cfg["mlflow"]
    feats_path = Path(cfg["features"]["output_path"]) / "train.parquet"
    df = pd.read_parquet(feats_path)

    X = df.drop(columns=[d["id_col"], d["target_col"]])
    y = df[d["target_col"]]
    X_tr, X_te, y_tr, y_te = train_test_split(
        X,
        y,
        test_size=cfg["split"]["test_size"],
        random_state=cfg["split"]["random_state"],
        stratify=y,
    )
    num_cols, cat_cols = split_columns(X, d["id_col"], d["target_col"])

    mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT_NAME", "utec-bank-attrition"))
    mlflow.sklearn.autolog(log_models=False, log_datasets=False, silent=True)
    tags = {
        "git_commit": git_commit(),
        "data_version": d["data_version"],
        "data_path": str(feats_path),
        "author": os.getenv("GITHUB_ACTOR", getpass.getuser()),
    }

    with mlflow.start_run(run_name="training_pipeline", tags=tags):
        mlflow.log_params(
            {
                "test_size": cfg["split"]["test_size"],
                "random_state": cfg["split"]["random_state"],
                "n_train": len(X_tr),
                "n_test": len(X_te),
            }
        )
        results = {}
        for name, params in tcfg["models"].items():
            results[name] = train_one(
                name,
                params,
                X_tr,
                y_tr,
                X_te,
                y_te,
                num_cols,
                cat_cols,
                tcfg["threshold"],
            )
            print(f"{name}: test_auc={results[name][1]['test_auc']:.4f}")

        sel = tcfg["selection_metric"]
        best = max(results, key=lambda k: results[k][1][sel])
        best_pipe, best_metrics = results[best]
        mlflow.set_tag("best_model", best)
        mlflow.log_metrics(best_metrics)

        example = X_te.head(5)
        info = mlflow.sklearn.log_model(
            best_pipe,
            name="model",
            signature=infer_signature(example, best_pipe.predict_proba(example)),
            input_example=example,
            pyfunc_predict_fn="predict_proba",
            serialization_format="cloudpickle",  # skops exige listar tipos confiables
            registered_model_name=mcfg["model_name"],
        )
        version = info.registered_model_version
        alias = promote(
            MlflowClient(),
            mcfg["model_name"],
            version,
            best_metrics["test_auc"],
            mcfg["min_auc_test"],
        )
        mlflow.set_tag("registry_alias", alias)
        print(f"Mejor: {best} | versión {version} | resultado: {alias}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    run(ap.parse_args().config)
