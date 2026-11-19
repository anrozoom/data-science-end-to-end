"""Tabla y gráfico por modelo del tuning, leídos desde MLflow (sin entrenar nada).

Para cada corrida padre de tuning terminada escribe en docs/tuning/:
  tuning_<modelo>.csv  mejor configuración, CV media ± desv., versión por defecto, mejora y si supera la desv.
  tuning_<modelo>.png  las 30 configuraciones ordenadas frente a la versión por defecto

Uso (desde pset_3/):  python src/resumen_tuning.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import pandas as pd

from experimento import EXPERIMENTO, configurar_mlflow

DOCS = Path(__file__).resolve().parents[1] / "docs" / "tuning"


def resumir(solo_nuevos: bool = False) -> list[str]:
    configurar_mlflow()
    exp = mlflow.get_experiment_by_name(EXPERIMENTO)
    r = mlflow.search_runs([exp.experiment_id], filter_string="tags.fase = 'tuning'", max_results=5000)
    if r.empty:
        return []
    DOCS.mkdir(parents=True, exist_ok=True)
    hechos = []
    padres = r[(r["tags.rol"] == "padre") & (r["status"] == "FINISHED")]
    for _, p in padres.iterrows():
        modelo = p["tags.modelo"]
        ruta_csv = DOCS / f"tuning_{modelo}.csv"
        if solo_nuevos and ruta_csv.exists():
            continue
        hijas = r[(r["tags.rol"] == "hija") & (r["tags.modelo"] == modelo)].copy()
        hijas = hijas.sort_values("metrics.cv_auc_pr_media", ascending=False)
        mejor = hijas.iloc[0]
        params = {c.replace("params.modelo__", ""): mejor[c] for c in hijas.columns
                  if c.startswith("params.modelo__") and pd.notna(mejor[c])}
        d_media, d_std = p["metrics.default_cv_auc_pr_media"], p["metrics.default_cv_auc_pr_std"]
        mejora = mejor["metrics.cv_auc_pr_media"] - d_media
        ruido = max(mejor["metrics.cv_auc_pr_std"], d_std)
        tabla = pd.DataFrame([{
            "modelo": modelo, "configuraciones": len(hijas),
            "mejor_cv_auc_pr_media": mejor["metrics.cv_auc_pr_media"], "mejor_cv_auc_pr_std": mejor["metrics.cv_auc_pr_std"],
            "mejor_auc_pr_entrenamiento": mejor["metrics.auc_pr_entrenamiento"], "mejor_brecha": mejor["metrics.brecha_auc_pr"],
            "defecto_cv_auc_pr_media": d_media, "defecto_cv_auc_pr_std": d_std,
            "mejora": mejora, "desviacion_de_referencia": ruido, "mejora_supera_desviacion": bool(mejora > ruido),
            "mejor_configuracion": json.dumps(params, ensure_ascii=False),
            "segundos_cv_promedio_por_configuracion": hijas["metrics.segundos_entrenamiento"].mean(),
            "run_id_padre": p["run_id"], "run_id_mejor_hija": mejor["run_id"],
        }])
        tabla.to_csv(ruta_csv, index=False)
        h = hijas.sort_values("metrics.cv_auc_pr_media").reset_index(drop=True)
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.errorbar(range(len(h)), h["metrics.cv_auc_pr_media"], yerr=h["metrics.cv_auc_pr_std"], fmt="o", ms=4,
                    color="#3b82f6", ecolor="#cbd5e1", label="configuración (± desv.)")
        ax.axhline(d_media, color="#ef4444", ls="--", label=f"por defecto {d_media:.4f}")
        ax.axhspan(d_media - d_std, d_media + d_std, color="#ef4444", alpha=.08)
        ax.set_title(f"{modelo}: {len(h)} configuraciones · mejora {mejora:+.4f} "
                     f"({'supera' if mejora > ruido else 'no supera'} la desv. {ruido:.4f})", fontsize=10)
        ax.set_xlabel("configuración (ordenadas por AUC-PR)"); ax.set_ylabel("AUC-PR CV"); ax.legend(fontsize=8)
        fig.tight_layout(); fig.savefig(DOCS / f"tuning_{modelo}.png", dpi=120); plt.close(fig)
        hechos.append(modelo)
    return hechos


if __name__ == "__main__":
    print("resumidos:", resumir())
