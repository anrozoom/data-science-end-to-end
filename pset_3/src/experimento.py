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


def borrar_corridas(fases: list[str]) -> int:
    """Borra (soft-delete) las corridas activas de estas fases para que Restart + Run All
    de un notebook no duplique corridas en el experimento."""
    exp = mlflow.get_experiment_by_name(EXPERIMENTO)
    previas = mlflow.search_runs([exp.experiment_id], output_format="list", max_results=50000)
    n = 0
    for r in previas:
        if r.data.tags.get("fase") in fases:
            mlflow.delete_run(r.info.run_id)
            n += 1
    return n


def entrenar_final(estimador, X, y, fraccion=FRACCION_LEGITIMAS):
    """Ajusta el pipeline con TODO el entrenamiento usando la misma estrategia que en la CV
    (todos los fraudes + una fracción fija de las legítimas)."""
    import time
    from sklearn.base import clone
    from pipeline import submuestrear, pesos_prevalencia_real, auc_pr

    y = np.asarray(y)
    idx = submuestrear(np.arange(len(y)), y, fraccion, SEMILLA + 100)
    modelo = clone(estimador)
    t0 = time.perf_counter()
    modelo.fit(X.iloc[idx], y[idx])
    segundos = time.perf_counter() - t0
    score = modelo.predict_proba(X.iloc[idx])[:, 1]
    return modelo, {"final_segundos_entrenamiento": segundos, "final_filas_ajuste": len(idx),
                    "final_auc_pr_entrenamiento": auc_pr(y[idx], score, pesos_prevalencia_real(y[idx], fraccion))}


def correr_modelo(nombre: str, familia: str, fase: str, estimador, X, y, monto, cv,
                  params: dict | None = None, registrar_artefacto: bool = True, nested: bool = False,
                  tags_extra: dict | None = None) -> dict:
    """CV + ajuste final + registro completo en MLflow. Devuelve un resumen y el run_id."""
    from pipeline import evaluar_cv

    with mlflow.start_run(run_name=nombre, nested=nested) as run:
        etiquetar(fase, familia, **(tags_extra or {}))
        registrar_datos()
        if params:
            mlflow.log_params({k: str(v) for k, v in params.items()})
        modelo_est = estimador.named_steps["modelo"] if hasattr(estimador, "named_steps") else estimador
        mlflow.log_params({f"modelo__{k}": str(v) for k, v in modelo_est.get_params().items()
                           if not callable(v) and len(str(v)) < 250})
        mlflow.log_param("modelo_clase", type(modelo_est).__name__)
        res = evaluar_cv(estimador, X, y, cv, monto=monto)
        registrar_resultado_cv(res)
        resumen = {"run_id": run.info.run_id, "nombre": nombre, "familia": familia, "fase": fase,
                   **{k: v for k, v in res.items() if isinstance(v, float)}}
        if registrar_artefacto:
            final, met = entrenar_final(estimador, X, y)
            mlflow.log_metrics(met)
            registrar_modelo(final, X)
            resumen.update(met)
            resumen["modelo_entrenado"] = final
        resumen["oof_indices"], resumen["oof_score"] = res["oof_indices"], res["oof_score"]
        resumen["pliegues"] = res["pliegues"]
    return resumen
