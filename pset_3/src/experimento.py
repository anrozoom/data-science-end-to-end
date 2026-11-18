"""Registro de corridas en el servidor de MLflow del PSet 3.

Cada corrida registra: parámetros (con la semilla), datos (tabla de origen, fecha de corte
y hash del snapshot), métricas (entrenamiento, media y desviación de la CV, segundos),
tags (fase, familia, commit de Git) y, si se pide, el pipeline entrenado con firma y
ejemplo de entrada (mlflow.sklearn.log_model, empaquetando src/ para que se pueda cargar).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import mlflow
import numpy as np
from mlflow.models import infer_signature

from datos import metadatos_snapshot
from pipeline import FRACCION_LEGITIMAS, SEMILLA

RAIZ = Path(__file__).resolve().parents[1]
EXPERIMENTO = "centinela"
NOMBRE_MODELO = "centinela-modelo"


def configurar_mlflow() -> str:
    """Apunta EXPLÍCITAMENTE al servidor del PSet 3 (pset_3/.env), no al del devcontainer."""
    env = RAIZ / ".env"
    uri = "http://127.0.0.1:5055"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if linea.startswith("MLFLOW_TRACKING_URI="):
                uri = linea.split("=", 1)[1].strip()
    os.environ["MLFLOW_TRACKING_URI"] = uri
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(EXPERIMENTO)
    return uri


def commit_git() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True,
                             text=True, check=True).stdout.strip()
        sucio = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=RAIZ,
                               capture_output=True, text=True).stdout.strip()
        return sha + ("-con-cambios" if sucio else "")
    except Exception:  # noqa: BLE001
        return "desconocido"


def registrar_datos() -> None:
    meta = metadatos_snapshot()
    mlflow.log_params({
        "datos_tabla_origen": meta["tabla_origen"],
        "datos_fecha_corte": meta["fecha_corte_snapshot"],
        "datos_sha256": meta["sha256"],
        "datos_filas_snapshot": meta["filas"],
        "semilla": SEMILLA,
        "cv_esquema": "TimeSeriesSplit(3) con ajuste submuestreado y validación completa",
        "cv_fraccion_legitimas_ajuste": FRACCION_LEGITIMAS,
    })


def registrar_resultado_cv(res: dict, prefijo: str = "") -> None:
    mlflow.log_metrics({
        f"{prefijo}auc_pr_entrenamiento": res["entrenamiento_auc_pr_media"],
        f"{prefijo}cv_auc_pr_media": res["cv_auc_pr_media"],
        f"{prefijo}cv_auc_pr_std": res["cv_auc_pr_std"],
        f"{prefijo}brecha_auc_pr": res["brecha_auc_pr"],
        f"{prefijo}segundos_entrenamiento": res["segundos_entrenamiento"],
        f"{prefijo}segundos_prediccion": res["segundos_prediccion"],
    })
    for _, f in res["pliegues"].iterrows():
        mlflow.log_metric(f"{prefijo}cv_auc_pr_pliegue", float(f["auc_pr_validacion"]), step=int(f["pliegue"]))
    if "cv_perdida_neta_oof" in res:
        mlflow.log_metric(f"{prefijo}cv_perdida_neta_oof", res["cv_perdida_neta_oof"])
        if np.isfinite(res["cv_umbral_optimo"]):
            mlflow.log_metric(f"{prefijo}cv_umbral_optimo", res["cv_umbral_optimo"])


def etiquetar(fase: str, familia: str, **extra) -> None:
    mlflow.set_tags({"fase": fase, "familia": familia, "git_commit": commit_git(), **extra})


def registrar_modelo(pipeline, X_ejemplo, nombre_artefacto: str = "modelo",
                     nombre_registro: str | None = None):
    """Guarda el pipeline entrenado con firma y ejemplo de entrada; empaqueta src/."""
    ejemplo = X_ejemplo.head(5)
    firma = infer_signature(ejemplo, pipeline.predict_proba(ejemplo)[:, 1])
    return mlflow.sklearn.log_model(
        pipeline, artifact_path=nombre_artefacto, signature=firma, input_example=ejemplo,
        code_paths=[str(RAIZ / "src" / "pipeline.py")],
        registered_model_name=nombre_registro,
    )
