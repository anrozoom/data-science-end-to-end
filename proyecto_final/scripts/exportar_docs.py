"""Exportes de la simulación y del experimento a docs/ (fuente: CENTINELA.PRODUCCION y el servidor de MLflow).

  docs/monitoreo.csv           PRODUCCION.MONITOREO de la simulación vigente (formato largo; pasos 0 a 25)
  docs/alertas.csv             PRODUCCION.ALERTAS (pasos 0 a 25)
  docs/reentrenamientos.csv    corridas de MLflow con fase = reentrenamiento + su decisión (PRODUCCION.REENTRENAMIENTOS)
  docs/corridas.csv            mlflow.search_runs de TODO el experimento "centinela" (PSet 3 + reentrenamientos)
  docs/predicciones.csv        MUESTRA trazable de PRODUCCION.PREDICCIONES (lotes 0 a 25): todos los fraudes con
                               target llegado + todas las alertas (verificar o retener) + el 1 % de las demás
                               (selección determinista: HASH(id_prediccion) % 100 = 0); cada fila con versión,
                               run_id, hash del snapshot y entradas
  docs/predicciones_por_lote.csv  agregado completo por lote, versión y decisión
  data/predicciones_completas.parquet  la tabla completa de la simulación (fuera de git: supera 100 MB en CSV)
Uso, desde proyecto_final/:  python scripts/exportar_docs.py [monitoreo alertas reentrenamientos corridas predicciones]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from produccion import FILTRO_SIM, INICIO_SIM_SQL, N_LOTES, NOMBRE_MODELO, Snowflake, configurar_mlflow  # noqa: E402

DOCS = RAIZ / "docs"


def monitoreo(sf):
    d = sf.sql(f"SELECT * FROM PRODUCCION.MONITOREO WHERE INICIO_SIMULACION = {INICIO_SIM_SQL} AND PASO < {N_LOTES} "
               "ORDER BY PASO, GRUPO, METRICA, VARIABLE")
    d.to_csv(DOCS / "monitoreo.csv", index=False)
    return f"monitoreo.csv: {len(d)} filas, pasos {d['paso'].min()} a {d['paso'].max()}"


def alertas(sf):
    d = sf.sql(f"SELECT * FROM PRODUCCION.ALERTAS WHERE INICIO_SIMULACION = {INICIO_SIM_SQL} AND PASO < {N_LOTES} ORDER BY PASO, ID_ALERTA")
    d.to_csv(DOCS / "alertas.csv", index=False)
    return f"alertas.csv: {len(d)} filas"


def _runs():
    import mlflow
    configurar_mlflow()
    return mlflow.search_runs(experiment_names=["centinela"], max_results=50_000)


def corridas(sf):
    r = _runs()
    r.to_csv(DOCS / "corridas.csv", index=False)
    return f"corridas.csv: {len(r)} corridas, por fase: {r['tags.fase'].value_counts().to_dict()}"


def reentrenamientos(sf):
    """Fuente principal: las etiquetas y métricas de cada corrida en MLflow (local, tiene todos los reentrenamientos).
    PRODUCCION.REENTRENAMIENTOS de la cuenta vigente solo completa la hora de la decisión: la simulación corrió en la
    cuenta original, suspendida el 27-nov (docs/simulacion/incidentes.md), y para esas corridas se conserva la hora del
    exporte anterior."""
    from mlflow import MlflowClient
    r = _runs()
    r = r[r["tags.fase"] == "reentrenamiento"].copy()
    version = {v.run_id: v.version for v in MlflowClient().search_model_versions(f"name='{NOMBRE_MODELO}'")}
    r["challenger_version"] = r["run_id"].map(version)
    r = r.rename(columns={"tags.paso": "paso", "params.lote_evaluacion": "lote_evaluacion", "tags.recomendacion": "recomendacion",
                          "tags.decision": "decision", "tags.motivo_decision": "motivo_decision"})
    try:
        d = sf.sql("SELECT RUN_ID, TS_DECISION FROM PRODUCCION.REENTRENAMIENTOS")
    except Exception:  # noqa: BLE001 - la tabla puede no existir en la cuenta vigente
        d = pd.DataFrame(columns=["run_id", "ts_decision"])
    r = r.merge(d, on="run_id", how="left")
    anterior = DOCS / "reentrenamientos.csv"
    if anterior.exists():
        previo = pd.read_csv(anterior)[["run_id", "ts_decision"]].rename(columns={"ts_decision": "ts_previo"})
        r = r.merge(previo, on="run_id", how="left")
        r["ts_decision"] = r["ts_decision"].astype(object).where(r["ts_decision"].notna(), r["ts_previo"])
    cols = ["run_id", "start_time", "tags.mlflow.runName", "tags.fase", "tags.motivo", "paso", "lote_evaluacion", "params.ventana",
            "params.champion_version", "challenger_version", "metrics.eval_perdida_x1000_champion",
            "metrics.eval_perdida_x1000_challenger", "metrics.mejora_x1000", "metrics.umbral_mejora_x1000",
            "metrics.eval_auc_pr_champion", "metrics.eval_auc_pr_challenger", "metrics.segundos_entrenamiento",
            "recomendacion", "decision", "motivo_decision", "ts_decision", "tags.git_commit", "params.datos_sha256"]
    r = r[[c for c in cols if c in r.columns]].sort_values("start_time")
    r.to_csv(anterior, index=False)
    return f"reentrenamientos.csv: {len(r)} corridas ({r['tags.motivo'].value_counts().to_dict()})"


def predicciones(sf):
    base = f"""SELECT p.ID_PREDICCION, p.TS_UTC, p.TRANS_NUM, p.LOTE, p.ORIGEN, p.PROBABILIDAD, p.DECISION,
                      p.UMBRAL_VERIFICAR, p.UMBRAL_RETENER, p.MODELO_NOMBRE, p.MODELO_VERSION, p.RUN_ID, p.RESPALDO,
                      p.LATENCIA_MS, t.IS_FRAUD, t.PASO_LLEGADA, l.DATOS_SHA256, p.ENTRADAS
               FROM PRODUCCION.PREDICCIONES p
               LEFT JOIN PRODUCCION.TARGETS_LLEGADOS t ON t.TRANS_NUM = p.TRANS_NUM AND t.LOTE = p.LOTE
               LEFT JOIN PRODUCCION.LOTES l ON l.TRANS_NUM = p.TRANS_NUM AND l.LOTE = p.LOTE
               WHERE p.{FILTRO_SIM.replace('LOTE IS', 'LOTE IS')} AND p.LOTE < {N_LOTES}"""
    base = base.replace("p.LOTE IS NOT NULL AND TS_UTC", "p.LOTE IS NOT NULL AND p.TS_UTC")
    completa = sf.sql(base)
    (RAIZ / "data").mkdir(exist_ok=True)
    completa.to_parquet(RAIZ / "data" / "predicciones_completas.parquet", index=False)
    fraude = completa["is_fraud"].fillna(0).astype(int) == 1
    alerta = completa["decision"].isin(["verificar", "retener"])
    import hashlib
    uno_pct = completa["id_prediccion"].map(lambda s: int(hashlib.sha256(s.encode()).hexdigest(), 16) % 100 == 0)
    m = completa[fraude | alerta | uno_pct].copy()
    m["motivo_muestra"] = ["fraude" if f else ("alerta" if a else "1% resto") for f, a in zip(fraude[m.index], alerta[m.index])]
    m.to_csv(DOCS / "predicciones.csv", index=False)
    ag = (completa.groupby(["lote", "modelo_version", "decision"])
          .agg(transacciones=("id_prediccion", "size"), fraudes=("is_fraud", "sum"),
               probabilidad_media=("probabilidad", "mean"), latencia_ms_media=("latencia_ms", "mean")).reset_index())
    ag.to_csv(DOCS / "predicciones_por_lote.csv", index=False)
    mb = (DOCS / "predicciones.csv").stat().st_size / 1e6
    return (f"predicciones.csv: {len(m)} de {len(completa)} predicciones ({mb:.1f} MB; {m['motivo_muestra'].value_counts().to_dict()}); "
            f"predicciones_por_lote.csv: {len(ag)} filas; data/predicciones_completas.parquet: {len(completa)} filas")


TAREAS = {"monitoreo": monitoreo, "alertas": alertas, "reentrenamientos": reentrenamientos, "corridas": corridas,
          "predicciones": predicciones}

if __name__ == "__main__":
    pedidas = sys.argv[1:] or list(TAREAS)
    sf = Snowflake()
    for t in pedidas:
        print(TAREAS[t](sf))
    sf.cerrar()
