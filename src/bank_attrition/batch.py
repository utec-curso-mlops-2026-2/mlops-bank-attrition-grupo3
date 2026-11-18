"""Inferencia batch: scorea el OOT con el modelo del Registry y calcula data drift."""

import argparse
import os
from datetime import date

import mlflow
import pandas as pd
from dotenv import load_dotenv
from mlflow.tracking import MlflowClient

from bank_attrition import data
from bank_attrition.features import load_config
from bank_attrition.monitoring import drift_report, psi_numeric, semaforo


def score(model, X: pd.DataFrame) -> pd.Series:
    proba = model.predict(X)
    proba = proba.iloc[:, 1] if isinstance(proba, pd.DataFrame) else proba[:, 1]
    return pd.Series(proba, index=X.index, name="prob_fuga")


def build_output(ids, prob, codmes: int, model_version: str) -> pd.DataFrame:
    out = pd.DataFrame({"id_cliente": ids.to_numpy(), "prob_fuga": prob.to_numpy()})
    # Decil 1 = mayor riesgo
    out["decil"] = (
        pd.qcut(prob.rank(method="first", ascending=False), 10, labels=False) + 1
    )
    out["segmento_riesgo"] = pd.cut(
        out["decil"], [0, 2, 5, 10], labels=["alto", "medio", "bajo"]
    )
    out["codmes_score"] = codmes
    out["fecha_score"] = date.today().isoformat()
    out["model_version"] = model_version
    return out.sort_values("prob_fuga", ascending=False, ignore_index=True)


def run(config_path: str = "config/config.yaml") -> None:
    load_dotenv()
    cfg = load_config(config_path)
    d, bcfg, mon = cfg["data"], cfg["batch"], cfg["monitoring"]
    feats = cfg["features"]["output_path"]
    codmes = cfg["features"]["corte"]["oot"]

    model_name, alias = cfg["mlflow"]["model_name"], bcfg["model_alias"]
    version = MlflowClient().get_model_version_by_alias(model_name, alias).version
    model = mlflow.pyfunc.load_model(f"models:/{model_name}@{alias}")

    oot, oot_info = data.read_parquet(data.join(feats, "oot.parquet"))
    ref, ref_info = data.read_parquet(data.join(feats, "train.parquet"))
    X_oot = oot.drop(columns=[d["id_col"]])
    X_ref = ref.drop(columns=[d["id_col"], d["target_col"]])
    num_cols = X_oot.select_dtypes(include="number").columns
    X_oot = X_oot.astype({c: "float64" for c in num_cols})
    X_ref = X_ref.astype({c: "float64" for c in num_cols})

    prob = score(model, X_oot)
    scores = build_output(oot[d["id_col"]], prob, codmes, version)

    # Drift: variables de entrada y distribución del score (train vs aplicación)
    report = drift_report(
        X_ref,
        X_oot,
        list(X_oot.columns),
        mon["bins"],
        mon["psi_alerta"],
        mon["psi_critico"],
    )
    psi_score = psi_numeric(score(model, X_ref), prob, mon["bins"])
    estado_score = semaforo(psi_score, mon["psi_alerta"], mon["psi_critico"])

    scores_info = data.write_csv(scores, data.join(bcfg["output_path"], codmes, "scores.csv"))
    report_info = data.write_csv(
        report, data.join(mon["output_path"], codmes, "psi_variables.csv")
    )

    mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT_NAME", "utec-bank-attrition"))
    tags = {
        "pipeline": "batch",
        "model_version": version,
        "data_version": d["data_version"],
        "data_path": oot_info["uri"],
        "data_sha256": oot_info["sha256"],
        "data_s3_version_id": str(oot_info["version_id"]),
        "reference_path": ref_info["uri"],
        "scores_path": scores_info["uri"],
    }
    with mlflow.start_run(run_name=f"batch_{codmes}", tags=tags):
        mlflow.log_params({"model_name": model_name, "alias": alias, "codmes": codmes})
        mlflow.log_metrics(
            {
                "psi_score": psi_score,
                "n_vars_alerta": int((report["estado"] == "alerta").sum()),
                "n_vars_critico": int((report["estado"] == "critico").sum()),
                "prob_fuga_media": float(prob.mean()),
                "n_clientes": len(scores),
            }
        )
        mlflow.set_tag("estado_score", estado_score)
        mlflow.log_text(report.to_csv(index=False), "monitoring/psi_variables.csv")

    print(f"Scores: {scores_info['uri']} ({len(scores)} clientes, modelo v{version})")
    print(f"Drift: {report_info['uri']}")
    print(
        f"PSI score: {psi_score:.4f} ({estado_score}) | "
        f"variables en alerta/crítico: {(report['estado'] != 'estable').sum()}"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    run(ap.parse_args().config)
