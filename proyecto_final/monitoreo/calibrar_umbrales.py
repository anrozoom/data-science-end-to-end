"""Umbrales del monitoreo y de la promoción, calibrados SOLO con la CV del champion del PSet 3.

1. Umbral de desempeño (deriva conceptual). Es la CV del PSet 3 llevada a escala semanal: las mismas
   predicciones fuera de pliegue (OOF) de la misma CV (HistGradientBoosting por defecto, TimeSeriesSplit(3),
   misma semilla), agrupadas en semanas de 7 días dentro de cada pliegue de validación (como los lotes).
   Umbral = media - 2 desviaciones de la AUC-PR semanal. Se descarta el umbral "por pliegue" (media - 2
   desviaciones de las 3 AUC-PR de pliegue, 0,961 ± 0,016 en el PSet 3) porque un pliegue tiene unas
   330.000 filas y una semana unas 17.800: la desviación entre pliegues subestima el ruido de un lote.
2. Banda de la tasa de alertas (verificar + retener) por semana: media ± 3 desviaciones de las semanas OOF.
3. Umbral de promoción: desviación (ddof=1) de la pérdida neta por 1.000 transacciones entre los 3 pliegues.
4. Soporte de entrenamiento (mínimo y máximo de cada numérica) y tasa de nulos, para las métricas de datos.

Verificación A POSTERIORI (no se usa para elegir nada): AUC-PR del champion en los 26 lotes de prueba SIN
alterar, para mostrar cuántas falsas alarmas daría cada umbral; y PSI natural de cada variable en esos
lotes, que justifica las variables excluidas del PSI.

Uso, desde proyecto_final/:  python monitoreo/calibrar_umbrales.py      (unos 3 minutos)
Salidas: docs/monitoreo/umbrales.json, semanas_oof.csv, falsas_alarmas_umbral.csv, psi_natural.csv,
         umbral_desempeno.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "monitoreo"))

from datos import cargar_obt, metadatos_snapshot  # noqa: E402
from deriva import EXCLUIDAS, NUMERICAS, PSI_ALERTA, PSI_AVISO, VIGILADAS, psi, referencia_misma_semana  # noqa: E402
from pipeline import (SEMILLA, CVTemporalSubmuestreada, auc_pr, construir_modelo, dividir, evaluar_cv,  # noqa: E402
                      perdida_neta)
from produccion import N_LOTES, lote_de  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.model_selection import TimeSeriesSplit  # noqa: E402

SALIDA = RAIZ / "docs" / "monitoreo"
MIN_FRAUDES_SEMANA = 10
CV_PSET3 = {"media": 0.961, "desviacion": 0.016}       # docs/seleccion y corrida 70bfd857 del champion


def main() -> dict:
    SALIDA.mkdir(parents=True, exist_ok=True)
    df = cargar_obt()
    Xe, ye, Xp, yp, ent, pru = dividir(df)
    api = json.loads((RAIZ / "docs" / "api" / "umbral_retener.json").read_text(encoding="utf-8"))
    u1, u2 = api["umbral_verificar_u1"], api["umbral_retener_u2"]
    y = ye.to_numpy()

    res = evaluar_cv(construir_modelo(HistGradientBoostingClassifier(random_state=SEMILLA)), Xe, ye,
                     CVTemporalSubmuestreada(), monto=ent["amt"].to_numpy())
    score = np.full(len(y), np.nan)
    score[res["oof_indices"]] = res["oof_score"]

    # ---- semanas de 7 días dentro de cada pliegue de validación (mismos cortes que la CV)
    semanas, perdidas_pliegue = [], []
    for k, (_, valid) in enumerate(TimeSeriesSplit(n_splits=3).split(Xe)):
        ts = ent["trans_ts"].iloc[valid]
        inicio = ts.min().normalize()
        nsem = ((ts.dt.normalize() - inicio).dt.days // 7).to_numpy()
        ultimo_completo = (ts.max().normalize() - inicio).days // 7 - (1 if (ts.max().normalize() - inicio).days % 7 < 6 else 0)
        v_y, v_s, v_m = y[valid], score[valid], ent["amt"].to_numpy()[valid]
        perdidas_pliegue.append(1000 * perdida_neta(v_y, v_s, v_m, u1) / len(valid))
        for s in range(int(ultimo_completo) + 1):
            m = nsem == s
            f = int(v_y[m].sum())
            semanas.append({"pliegue": k, "semana": s, "desde": (inicio + pd.Timedelta(days=7 * s)).date(),
                            "filas": int(m.sum()), "fraudes": f,
                            "auc_pr": auc_pr(v_y[m], v_s[m]) if f >= MIN_FRAUDES_SEMANA else np.nan,
                            "tasa_alertas": float((v_s[m] >= u1).mean()), "tasa_retener": float((v_s[m] >= u2).mean()),
                            "perdida_x1000": 1000 * perdida_neta(v_y[m], v_s[m], v_m[m], u1) / m.sum()})
    S = pd.DataFrame(semanas)
    S.to_csv(SALIDA / "semanas_oof.csv", index=False)
    a = S["auc_pr"].dropna()
    media, desv = float(a.mean()), float(a.std(ddof=1))
    umbral_semanal = media - 2 * desv
    umbral_pliegue = CV_PSET3["media"] - 2 * CV_PSET3["desviacion"]
    ta = S["tasa_alertas"]

    # ---- verificación a posteriori en los lotes de prueba SIN alterar (champion = mismo modelo de la CV ajustado a todo)
    import mlflow
    champion = mlflow.sklearn.load_model(str(RAIZ / "tests" / "fixtures" / "modelo_champion"))
    lote = lote_de(pru["trans_ts"])
    p = champion.predict_proba(Xp)[:, 1]
    lotes = []
    for k in range(N_LOTES):
        m = lote == k
        f = int(yp.to_numpy()[m].sum())
        lotes.append({"lote": k, "filas": int(m.sum()), "fraudes": f,
                      "auc_pr_sin_alterar": auc_pr(yp.to_numpy()[m], p[m]) if f else np.nan})
    L = pd.DataFrame(lotes)
    L["bajo_umbral_pliegue"] = L["auc_pr_sin_alterar"] < umbral_pliegue
    L["bajo_umbral_semanal"] = L["auc_pr_sin_alterar"] < umbral_semanal
    L.to_csv(SALIDA / "falsas_alarmas_umbral.csv", index=False)

    def consecutivas(serie):
        b = serie.to_numpy()
        return int(sum(b[i] and b[i + 1] for i in range(len(b) - 1)))

    S_ok = S.dropna(subset=["auc_pr"])
    comparacion = {
        "umbral_por_pliegue": {"valor": umbral_pliegue, "regla": "media - 2 desv. de las 3 AUC-PR de pliegue (PSet 3: 0,961 ± 0,016)",
                               "semanas_oof_bajo_umbral": int((S_ok["auc_pr"] < umbral_pliegue).sum()),
                               "lotes_prueba_sin_alterar_bajo_umbral": L.loc[L["bajo_umbral_pliegue"], "lote"].tolist()},
        "umbral_semanal": {"valor": umbral_semanal, "regla": "media - 2 desv. de la AUC-PR OOF semanal de la misma CV",
                           "semanas_oof_bajo_umbral": int((S_ok["auc_pr"] < umbral_semanal).sum()),
                           "pares_consecutivos_oof_bajo_umbral": consecutivas(S_ok["auc_pr"] < umbral_semanal),
                           "lotes_prueba_sin_alterar_bajo_umbral": L.loc[L["bajo_umbral_semanal"], "lote"].tolist()},
    }

    # ---- PSI natural en los lotes SIN alterar (referencia: misma semana de 2019)
    filas = []
    for k in range(N_LOTES):
        act = pru[lote == k]
        ref = referencia_misma_semana(ent, act["trans_ts"].min(), act["trans_ts"].max())
        for v in VIGILADAS + list(EXCLUIDAS):
            if v in EXCLUIDAS:
                from deriva import psi_categorica, psi_numerica
                valor = psi_numerica(ref[v], act[v]) if v == "n_tx_previas" else psi_categorica(ref[v], act[v])
            else:
                valor = psi(v, ref, act)
            filas.append({"lote": k, "variable": v, "vigilada": v not in EXCLUIDAS, "psi": valor,
                          "filas_lote": len(act), "filas_referencia": len(ref)})
    P = pd.DataFrame(filas)
    P.to_csv(SALIDA / "psi_natural.csv", index=False)
    resumen_psi = (P.groupby(["variable", "vigilada"])["psi"].agg(["median", "max"]).reset_index()
                   .sort_values("max", ascending=False))

    resultado = {
        "fuente": "CV del champion del PSet 3 (HistGradientBoosting por defecto, TimeSeriesSplit(3), semilla 42)",
        "datos_sha256": metadatos_snapshot()["sha256"],
        "umbral_verificar_u1": u1, "umbral_retener_u2": u2,
        "cv_auc_pr_pliegues_recalculada": res["pliegues"]["auc_pr_validacion"].round(6).tolist(),
        "desempeno": {
            "semanas_oof": int(len(S)), "semanas_con_auc": int(len(a)), "min_fraudes_por_semana": MIN_FRAUDES_SEMANA,
            "auc_pr_semanal_media": media, "auc_pr_semanal_desviacion": desv,
            "auc_pr_semanal_min": float(a.min()), "auc_pr_semanal_p5": float(a.quantile(0.05)),
            "umbral_auc_pr": umbral_semanal, "lotes_consecutivos_para_reentrenar": 2,
            "comparacion": comparacion,
        },
        "tasa_alertas": {"media": float(ta.mean()), "desviacion": float(ta.std(ddof=1)),
                         "banda_min": float(max(0.0, ta.mean() - 3 * ta.std(ddof=1))),
                         "banda_max": float(ta.mean() + 3 * ta.std(ddof=1))},
        "promocion": {"perdida_x1000_por_pliegue": perdidas_pliegue,
                      "umbral_mejora_x1000": float(np.std(perdidas_pliegue, ddof=1)),
                      "regla": "promover si pérdida/1000 del champion - pérdida/1000 del challenger > desv. entre pliegues, en el mismo lote"},
        "volumen": {"banda_relativa_misma_semana_2019": [0.7, 1.3]},
        "psi": {"aviso": PSI_AVISO, "alerta": PSI_ALERTA, "vigiladas": VIGILADAS, "excluidas": EXCLUIDAS,
                "max_natural_vigiladas": float(P.loc[P["vigilada"], "psi"].max()),
                "resumen_natural": resumen_psi.round(4).to_dict(orient="records")},
        "soporte": {v: [float(Xe[v].min()), float(Xe[v].max())] for v in NUMERICAS},
        "nulos_referencia": {v: float(Xe[v].isna().mean()) for v in NUMERICAS},
        "datos": {"fuera_de_soporte_max": 0.01},
    }
    (SALIDA / "umbrales.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False, default=float), encoding="utf-8")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(range(len(S_ok)), S_ok["auc_pr"], "o-", ms=3, color="#3b82f6", label="AUC-PR OOF por semana (CV del PSet 3)")
    ax.axhline(umbral_semanal, color="#ef4444", ls="--", label=f"umbral semanal = {umbral_semanal:.4f}")
    ax.axhline(umbral_pliegue, color="#f59e0b", ls=":", label=f"umbral por pliegue = {umbral_pliegue:.4f} (descartado)")
    ax.set_xlabel("semana de validación (3 pliegues, en orden)"); ax.set_ylabel("AUC-PR")
    ax.set_title("Umbral de desempeño: la CV del PSet 3 llevada a escala semanal"); ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout(); fig.savefig(SALIDA / "umbral_desempeno.png", dpi=120); plt.close(fig)
    return resultado


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: r[k] for k in ("cv_auc_pr_pliegues_recalculada", "desempeno", "tasa_alertas", "promocion")},
                     indent=2, ensure_ascii=False, default=float))
    print(json.dumps(r["psi"]["resumen_natural"][:8], indent=1, ensure_ascii=False))
