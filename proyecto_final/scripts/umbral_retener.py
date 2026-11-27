"""Segundo umbral de decisión (retener) del champion, elegido SOLO con la CV del entrenamiento.

Regla (docs/cambios.md): retener desde el puntaje más bajo u2 tal que, entre las predicciones fuera de
pliegue (OOF) de la CV con puntaje >= u2, al menos el 90 % sean fraude. Así la cola del analista tiene
sobre todo fraudes. Nunca se usa la partición de prueba.

Acciones del PSet 1:  aprobar  < u1 (0,2400, umbral por costo del PSet 3) <=  verificar  < u2 <=  retener

Reproduce la CV del champion del PSet 3 (HistGradientBoosting por defecto, misma semilla y pliegues),
reporta cuántas alertas por día genera cada acción en los días de validación y guarda el resultado en
docs/api/umbral_retener.json (y un gráfico). Con --registrar, agrega u2 como tag de la versión champion.

Uso, desde proyecto_final/:  python scripts/umbral_retener.py [--registrar]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from datos import cargar_obt, metadatos_snapshot  # noqa: E402
from pipeline import (SEMILLA, CVTemporalSubmuestreada, construir_modelo, dividir, evaluar_cv,  # noqa: E402
                      resumen_negocio)
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

PRECISION_OBJETIVO = 0.90
DOCS = RAIZ / "docs" / "api"


def main(registrar: bool) -> dict:
    df = cargar_obt()
    X, y, _, _, ent, _ = dividir(df)
    res = evaluar_cv(construir_modelo(HistGradientBoostingClassifier(random_state=SEMILLA)), X, y,
                     CVTemporalSubmuestreada(), monto=ent["amt"].to_numpy())
    idx, s = res["oof_indices"], res["oof_score"]
    yy, fechas = y.to_numpy()[idx], ent["trans_ts"].dt.date.to_numpy()[idx]
    u1 = res["cv_umbral_optimo"]

    # Precisión acumulada desde el puntaje más alto hacia abajo: el u2 más bajo con precisión >= objetivo.
    orden = np.argsort(-s, kind="mergesort")
    s_ord, y_ord = s[orden], yy[orden]
    prec = np.cumsum(y_ord) / np.arange(1, len(y_ord) + 1)
    ultimo_de_empate = np.r_[s_ord[1:] != s_ord[:-1], True]
    candidatos = np.where(ultimo_de_empate & (prec >= PRECISION_OBJETIVO))[0]
    k = int(candidatos.max())                         # el corte más profundo que mantiene la precisión
    u2 = float(s_ord[k])

    dec = np.where(s >= u2, "retener", np.where(s >= u1, "verificar", "aprobar"))
    por_dia = pd.DataFrame({"fecha": fechas, "decision": dec}).groupby(["fecha", "decision"]).size().unstack(fill_value=0)
    dias = int(por_dia.shape[0])
    tabla = pd.DataFrame({
        "decision": ["aprobar", "verificar", "retener"],
        "transacciones": [int((dec == d).sum()) for d in ("aprobar", "verificar", "retener")],
        "fraudes": [int(yy[dec == d].sum()) for d in ("aprobar", "verificar", "retener")],
    })
    tabla["precision"] = (tabla["fraudes"] / tabla["transacciones"].clip(lower=1)).round(4)
    tabla["pct_de_los_fraudes"] = (100 * tabla["fraudes"] / yy.sum()).round(2)
    tabla["por_dia_promedio"] = [round(float(por_dia.get(d, pd.Series(0)).mean()), 1) for d in tabla["decision"]]
    tabla["por_dia_p95"] = [round(float(por_dia.get(d, pd.Series(0)).quantile(.95)), 1) for d in tabla["decision"]]

    alertas_dia = por_dia.reindex(columns=["verificar", "retener"], fill_value=0).sum(axis=1)
    franjas = pd.DataFrame({
        "franja": [f"verificar ({u1:.2f} a {u2:.2f})", f"retener ({u2:.2f} o más)", "total de alertas (verificar + retener)"],
        "por_dia_promedio": [round(float(por_dia.get("verificar", pd.Series(0)).mean()), 1),
                             round(float(por_dia.get("retener", pd.Series(0)).mean()), 1), round(float(alertas_dia.mean()), 1)],
        "por_dia_p95": [round(float(por_dia.get("verificar", pd.Series(0)).quantile(.95)), 1),
                        round(float(por_dia.get("retener", pd.Series(0)).quantile(.95)), 1), round(float(alertas_dia.quantile(.95)), 1)],
        "por_dia_maximo": [int(por_dia.get("verificar", pd.Series(0)).max()), int(por_dia.get("retener", pd.Series(0)).max()),
                           int(alertas_dia.max())],
    })
    franjas.to_csv(DOCS / "alertas_por_dia_franjas.csv", index=False)
    resultado = {
        "regla": f"u2 = menor puntaje con precisión OOF >= {PRECISION_OBJETIVO:.0%} entre las alertas con puntaje >= u2",
        "modelo": "centinela-modelo@champion (HistGradientBoosting por defecto, PSet 3)",
        "datos_sha256": metadatos_snapshot()["sha256"],
        "oof_filas": int(len(s)), "oof_fraudes": int(yy.sum()), "oof_dias": dias,
        "umbral_verificar_u1": u1, "umbral_retener_u2": u2,
        "precision_en_u2": float(prec[k]), "alertas_retener_oof": int(k + 1),
        "cv_auc_pr_media": res["cv_auc_pr_media"], "cv_perdida_neta_oof": res["cv_perdida_neta_oof"],
        "negocio_oof_con_u1": resumen_negocio(yy, s, ent["amt"].to_numpy()[idx], u1),
        "decisiones": tabla.to_dict(orient="records"),
        "alertas_por_dia_franjas_excluyentes": franjas.to_dict(orient="records"),
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "umbral_retener.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    tabla.to_csv(DOCS / "decisiones_oof_por_accion.csv", index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    paso = max(1, len(s_ord) // 4000)
    ax.plot(s_ord[::paso], prec[::paso], color="#3b82f6", label="precisión de alertas con puntaje >= umbral")
    ax.axhline(PRECISION_OBJETIVO, color="#ef4444", ls="--", label=f"objetivo {PRECISION_OBJETIVO:.0%}")
    ax.axvline(u1, color="#f59e0b", ls=":", label=f"u1 verificar = {u1:.4f}")
    ax.axvline(u2, color="#ef4444", ls=":", label=f"u2 retener = {u2:.4f}")
    ax.set_xlabel("umbral (puntaje del modelo)"); ax.set_ylabel("precisión"); ax.set_ylim(0, 1.02)
    ax.set_title("Precisión de las alertas según el umbral (predicciones OOF de la CV)"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(DOCS / "umbral_retener.png", dpi=120); plt.close(fig)

    if registrar:
        import mlflow
        from mlflow import MlflowClient
        env = (RAIZ / ".env").read_text().splitlines()
        mlflow.set_tracking_uri(next((l.split("=", 1)[1] for l in env if l.startswith("MLFLOW_TRACKING_URI=")), "http://127.0.0.1:5055"))
        c = MlflowClient()
        v = c.get_model_version_by_alias("centinela-modelo", "champion")
        c.set_model_version_tag("centinela-modelo", v.version, "umbral_retener", repr(u2))
        c.set_model_version_tag("centinela-modelo", v.version, "umbral_retener_regla", resultado["regla"])
        resultado["registrado_en_version"] = v.version
    return resultado


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--registrar", action="store_true")
    r = main(p.parse_args().registrar)
    print(json.dumps({k: v for k, v in r.items() if k != "negocio_oof_con_u1"}, indent=2, ensure_ascii=False, default=float))
