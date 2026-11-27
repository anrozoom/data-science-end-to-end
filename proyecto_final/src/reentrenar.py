"""Reentrenamiento del modelo de Centinela (lo llama kestra/reentrenamiento.yml).

entrenar --paso k --motivo {desempeño|calendario}
  - Lote de evaluación L = k - 2: el lote etiquetado más reciente. NINGUNO de los dos modelos lo vio.
  - Ventana: todo el entrenamiento del PSet 3 + los lotes etiquetados 0..L-1, con las entradas tal como las
    recibió la API (PRODUCCION.LOTES) y su target ya llegado (PRODUCCION.TARGETS_LLEGADOS). Los 4 lotes más
    recientes de la ventana pesan 5 veces más (unas 7.000 a 14.000 filas por lote frente a 1,3 M de
    entrenamiento; sin peso, la deriva apenas se notaría).
  - Mismo pipeline y mismos hiperparámetros del champion vigente (sklearn.clone), mismo submuestreo
    (todos los fraudes + 5 % de las legítimas, semilla 142). Sin tuning. Mismos umbrales de decisión.
  - Corrida de MLflow con tag fase=reentrenamiento y el motivo; nueva versión de centinela-modelo con alias
    challenger. Champion y challenger se evalúan en el lote L con la pérdida neta por 1.000 transacciones.
  - Regla de promoción: mejora (champion - challenger) > desviación entre pliegues de la CV (umbrales.json).
  - Fila en PRODUCCION.REENTRENAMIENTOS con la recomendación; la decisión queda "pendiente" (Pause).
decidir --paso k --aprobar {true|false} --motivo "..."
  - Aprobado: el alias champion pasa a la versión nueva; la API la carga con POST /recargar (sin reconstruir
    la imagen) y se verifica en GET /modelo. Rechazado: el champion no cambia y se registra el motivo.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from datos import cargar_obt, metadatos_snapshot  # noqa: E402
from pipeline import FRACCION_LEGITIMAS, SEMILLA, auc_pr, dividir, perdida_neta, submuestrear  # noqa: E402
from produccion import (HORIZONTE, INICIO_SIM_SQL, N_RECIENTES, NOMBRE_MODELO, PESO_RECIENTES, Snowflake,  # noqa: E402
                        configurar_mlflow, emitir_salidas, tipar, umbrales)

API = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")

DDL_REENTRENAMIENTOS = """CREATE TABLE IF NOT EXISTS PRODUCCION.REENTRENAMIENTOS (
    INICIO_SIMULACION TIMESTAMP_NTZ, PASO NUMBER, MOTIVO VARCHAR, LOTE_EVALUACION NUMBER, VENTANA_HASTA_LOTE NUMBER,
    FILAS_VENTANA_PRODUCCION NUMBER, FILAS_AJUSTE NUMBER, CHAMPION_VERSION VARCHAR, CHALLENGER_VERSION VARCHAR,
    RUN_ID VARCHAR, AUC_PR_CHAMPION FLOAT, AUC_PR_CHALLENGER FLOAT, PERDIDA_X1000_CHAMPION FLOAT,
    PERDIDA_X1000_CHALLENGER FLOAT, PERDIDA_USD_CHAMPION FLOAT, PERDIDA_USD_CHALLENGER FLOAT, MEJORA_X1000 FLOAT,
    UMBRAL_MEJORA_X1000 FLOAT, RECOMENDACION VARCHAR, DECISION VARCHAR, TS_ENTRENAMIENTO TIMESTAMP_NTZ,
    SEGUNDOS_ENTRENAMIENTO FLOAT, MOTIVO_DECISION VARCHAR, TS_DECISION TIMESTAMP_NTZ)"""


def _commit() -> str:
    if os.environ.get("GIT_COMMIT"):
        return os.environ["GIT_COMMIT"]
    from experimento import commit_git
    return commit_git()


def lotes_etiquetados(sf: Snowflake, hasta: int, tabla_target: str = "TARGETS_LLEGADOS") -> pd.DataFrame:
    return sf.sql(f"""SELECT l.*, t.IS_FRAUD FROM PRODUCCION.LOTES l
                      JOIN PRODUCCION.{tabla_target} t ON t.TRANS_NUM = l.TRANS_NUM AND t.LOTE = l.LOTE
                      WHERE l.LOTE <= {hasta} ORDER BY l.TRANS_TS, l.TRANS_NUM""")


def evaluar(modelo, X: pd.DataFrame, y: np.ndarray, u1: float) -> dict:
    s = modelo.predict_proba(X)[:, 1]
    return {"auc_pr": auc_pr(y, s), "perdida_neta": perdida_neta(y, s, X["amt"].to_numpy(), u1),
            "perdida_x1000": 1000 * perdida_neta(y, s, X["amt"].to_numpy(), u1) / len(y)}


def entrenar(paso: int, motivo: str, ensayo: bool = False) -> dict:
    """ensayo=True: mismos datos y ajuste, pero targets de TARGETS (aún no "llegados"), modelo guardado solo en
    una carpeta temporal y sin escribir en MLflow ni en Snowflake (para medir tiempos y validar el código)."""
    import mlflow
    from mlflow import MlflowClient
    from sklearn.base import clone
    from experimento import EXPERIMENTO, registrar_modelo

    t0 = time.time()
    u = umbrales()
    umbral_mejora = u["promocion"]["umbral_mejora_x1000"]
    configurar_mlflow()
    mlflow.set_experiment(EXPERIMENTO)
    c = MlflowClient()
    vc = c.get_model_version_by_alias(NOMBRE_MODELO, "champion")
    champion = mlflow.sklearn.load_model(f"models:/{NOMBRE_MODELO}/{vc.version}")
    u1, u2 = float(vc.tags["umbral_decision"]), float(vc.tags["umbral_retener"])

    sf = Snowflake()
    inicio = sf.sql(f"SELECT {INICIO_SIM_SQL} AS i")["i"].iloc[0]
    L = paso - HORIZONTE
    etiq = lotes_etiquetados(sf, L, "TARGETS" if ensayo else "TARGETS_LLEGADOS")
    if L < 1 or etiq.empty:
        raise RuntimeError(f"No hay lotes etiquetados suficientes en el paso {paso}")
    ev = etiq[etiq["lote"] == L]
    ventana = etiq[etiq["lote"] < L]

    Xe, ye, _, _, _, _ = dividir(cargar_obt())
    Xv, yv = tipar(ventana), ventana["is_fraud"].to_numpy().astype(int)
    X = pd.concat([Xe, Xv], ignore_index=True)
    y = np.concatenate([ye.to_numpy(), yv])
    peso = np.concatenate([np.ones(len(ye)), np.where(ventana["lote"].to_numpy() >= L - N_RECIENTES, PESO_RECIENTES, 1.0)])
    idx = submuestrear(np.arange(len(y)), y, FRACCION_LEGITIMAS, SEMILLA + 100)
    challenger = clone(champion)
    t1 = time.perf_counter()
    challenger.fit(X.iloc[idx], y[idx], modelo__sample_weight=peso[idx])
    seg_fit = time.perf_counter() - t1

    Xev, yev = tipar(ev), ev["is_fraud"].to_numpy().astype(int)
    m_ch, m_nu = evaluar(champion, Xev, yev, u1), evaluar(challenger, Xev, yev, u1)
    mejora = m_ch["perdida_x1000"] - m_nu["perdida_x1000"]
    recomendacion = "promover" if mejora > umbral_mejora else "rechazar"

    if ensayo:
        import tempfile
        from mlflow.models import infer_signature
        with tempfile.TemporaryDirectory() as d:
            mlflow.sklearn.save_model(challenger, f"{d}/m", signature=infer_signature(Xev.head(5), challenger.predict_proba(Xev.head(5))[:, 1]),
                                      input_example=Xev.head(5), code_paths=[str(RAIZ / "src" / "pipeline.py")])
            recargado = mlflow.sklearn.load_model(f"{d}/m")
            assert np.allclose(recargado.predict_proba(Xev)[:, 1], challenger.predict_proba(Xev)[:, 1])
        sf.cerrar()
        res = {"ensayo": True, "paso": paso, "lote_evaluacion": L, "filas_ventana": len(ventana), "filas_ajuste": len(idx),
               "segundos_ajuste": round(seg_fit, 1), "segundos_total": round(time.time() - t0, 1),
               "champion": {k: round(v, 4) for k, v in m_ch.items()}, "challenger": {k: round(v, 4) for k, v in m_nu.items()},
               "mejora_x1000": round(mejora, 2), "umbral": round(umbral_mejora, 2), "recomendacion": recomendacion}
        print(res)
        return res

    with mlflow.start_run(run_name=f"reentrenamiento_paso_{paso:02d}") as run:
        mlflow.set_tags({"fase": "reentrenamiento", "familia": "HistGradientBoosting", "git_commit": _commit(),
                         "motivo": motivo, "paso": str(paso), "inicio_simulacion": str(inicio),
                         "recomendacion": recomendacion})
        meta = metadatos_snapshot()
        mlflow.log_params({
            "champion_version": vc.version, "champion_run_id": vc.run_id, "semilla": SEMILLA,
            "fraccion_legitimas_ajuste": FRACCION_LEGITIMAS, "peso_lotes_recientes": PESO_RECIENTES,
            "n_lotes_recientes": N_RECIENTES, "ventana": f"entrenamiento PSet 3 + lotes 0..{L - 1}",
            "lote_evaluacion": L, "datos_tabla_origen": meta["tabla_origen"] + " + CENTINELA.PRODUCCION.LOTES/TARGETS_LLEGADOS",
            "datos_sha256": meta["sha256"], "datos_fecha_corte": meta["fecha_corte_snapshot"],
            "umbral_verificar": u1, "umbral_retener": u2, "regla_promocion": u["promocion"]["regla"],
            **{f"modelo__{k}": str(v) for k, v in challenger.named_steps["modelo"].get_params().items() if len(str(v)) < 250}})
        mlflow.log_metrics({
            "filas_ajuste": len(idx), "fraudes_ajuste": int(y[idx].sum()), "filas_ventana_produccion": len(ventana),
            "segundos_entrenamiento": seg_fit, "umbral_mejora_x1000": umbral_mejora, "mejora_x1000": mejora,
            **{f"eval_{k}_champion": v for k, v in m_ch.items()}, **{f"eval_{k}_challenger": v for k, v in m_nu.items()}})
        info = registrar_modelo(challenger, Xev, nombre_registro=NOMBRE_MODELO)
        run_id = run.info.run_id
    version = str(info.registered_model_version)
    for k, v in {"umbral_decision": repr(u1), "umbral_retener": repr(u2), "fase": "reentrenamiento", "motivo": motivo,
                 "paso": str(paso), "recomendacion": recomendacion, "decision": "pendiente"}.items():
        c.set_model_version_tag(NOMBRE_MODELO, version, k, v)
    c.set_registered_model_alias(NOMBRE_MODELO, "challenger", version)

    fila = pd.DataFrame([{
        "inicio_simulacion": inicio, "paso": paso, "motivo": motivo, "lote_evaluacion": L,
        "ventana_hasta_lote": L - 1, "filas_ventana_produccion": len(ventana), "filas_ajuste": len(idx),
        "champion_version": vc.version, "challenger_version": version, "run_id": run_id,
        "auc_pr_champion": m_ch["auc_pr"], "auc_pr_challenger": m_nu["auc_pr"],
        "perdida_x1000_champion": m_ch["perdida_x1000"], "perdida_x1000_challenger": m_nu["perdida_x1000"],
        "perdida_usd_champion": m_ch["perdida_neta"], "perdida_usd_challenger": m_nu["perdida_neta"],
        "mejora_x1000": mejora, "umbral_mejora_x1000": umbral_mejora, "recomendacion": recomendacion,
        "decision": "pendiente", "motivo_decision": None, "ts_entrenamiento": pd.Timestamp.utcnow().tz_localize(None),
        "ts_decision": pd.NaT, "segundos_entrenamiento": seg_fit}])
    sf.ejecutar(DDL_REENTRENAMIENTOS)              # tipos explícitos: con write_pandas, una columna vacía quedaría NUMBER
    if sf.existe("REENTRENAMIENTOS"):
        sf.ejecutar(f"DELETE FROM PRODUCCION.REENTRENAMIENTOS WHERE PASO = {paso} AND INICIO_SIMULACION = {INICIO_SIM_SQL}")
    sf.escribir(fila, "REENTRENAMIENTOS")
    sf.cerrar()

    mensaje = (f"PASO {paso} | disparo: {motivo} | evaluación en el lote {L} (ninguno lo vio) | "
               f"champion v{vc.version}: pérdida/1000 {m_ch['perdida_x1000']:.2f} (AUC-PR {m_ch['auc_pr']:.4f}) | "
               f"challenger v{version}: pérdida/1000 {m_nu['perdida_x1000']:.2f} (AUC-PR {m_nu['auc_pr']:.4f}) | "
               f"mejora {mejora:+.2f} frente a {umbral_mejora:.2f} -> la regla recomienda {recomendacion.upper()}")
    print(mensaje)
    print(f"Ventana: entrenamiento + lotes 0..{L - 1} ({len(ventana)} filas de producción); ajuste con {len(idx)} filas "
          f"en {seg_fit:.1f} s; corrida {run_id}; total {time.time() - t0:.0f} s")
    res = {"paso": paso, "motivo": motivo, "lote_evaluacion": L, "champion_version": vc.version,
           "challenger_version": version, "perdida_x1000_champion": round(m_ch["perdida_x1000"], 2),
           "perdida_x1000_challenger": round(m_nu["perdida_x1000"], 2), "mejora_x1000": round(mejora, 2),
           "umbral_mejora_x1000": round(umbral_mejora, 2), "recomendacion": recomendacion, "run_id": run_id,
           "mensaje": mensaje}
    emitir_salidas(**res)
    return res


def decidir(paso: int, aprobar: bool, motivo: str) -> dict:
    import requests
    from mlflow import MlflowClient

    configurar_mlflow()
    c = MlflowClient()
    sf = Snowflake()
    r = sf.sql(f"SELECT * FROM PRODUCCION.REENTRENAMIENTOS WHERE PASO = {paso} AND INICIO_SIMULACION = {INICIO_SIM_SQL}")
    if r.empty:
        raise RuntimeError(f"No hay un reentrenamiento del paso {paso} en esta simulación")
    r = r.iloc[0]
    nueva, anterior = str(r["challenger_version"]), str(r["champion_version"])
    decision = "aprobada" if aprobar else "rechazada"
    coincide = (decision == "aprobada") == (r["recomendacion"] == "promover")
    c.set_model_version_tag(NOMBRE_MODELO, nueva, "decision", decision)
    c.set_model_version_tag(NOMBRE_MODELO, nueva, "motivo_decision", motivo or "")
    c.set_tag(r["run_id"], "decision", decision)
    c.set_tag(r["run_id"], "motivo_decision", motivo or "")
    en_uso = None
    if aprobar:
        c.set_registered_model_alias(NOMBRE_MODELO, "champion", nueva)
        c.set_model_version_tag(NOMBRE_MODELO, anterior, "reemplazada_en_paso", str(paso))
        token = os.environ.get("ADMIN_TOKEN", "")
        fin = time.time() + 120
        while time.time() < fin:
            if token:
                requests.post(f"{API}/recargar", headers={"X-Token": token}, timeout=60)
            en_uso = str(requests.get(f"{API}/modelo", timeout=10).json().get("version"))
            if en_uso == nueva:
                break
            time.sleep(5)
        if en_uso != nueva:
            raise RuntimeError(f"La API sigue con la versión {en_uso} y no con la {nueva}")
    sf.ejecutar("""UPDATE PRODUCCION.REENTRENAMIENTOS SET DECISION = %s, MOTIVO_DECISION = %s, TS_DECISION = SYSDATE()
                   WHERE PASO = %s AND INICIO_SIMULACION = (SELECT MAX(INICIO_UTC) FROM PRODUCCION.SIMULACION)""",
                (decision, motivo or "", paso))
    sf.cerrar()
    print(f"PASO {paso}: promoción {decision.upper()} ({'coincide' if coincide else 'NO coincide'} con la regla, que "
          f"recomendaba {r['recomendacion']}). Motivo: {motivo or '(sin motivo)'}. "
          + (f"Champion: v{anterior} -> v{nueva}; la API ya sirve la v{en_uso}." if aprobar else f"El champion sigue en v{anterior}."))
    res = {"paso": paso, "decision": decision, "coincide_con_regla": coincide, "champion": nueva if aprobar else anterior}
    emitir_salidas(**res)
    return res


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    sub = a.add_subparsers(dest="accion", required=True)
    e = sub.add_parser("entrenar")
    e.add_argument("--paso", type=int, required=True)
    e.add_argument("--motivo", required=True)
    e.add_argument("--ensayo", action="store_true")
    d = sub.add_parser("decidir")
    d.add_argument("--paso", type=int, required=True)
    d.add_argument("--aprobar", required=True, choices=["true", "false"])
    d.add_argument("--motivo", default="")
    d.add_argument("--motivo-b64", default="", help="motivo en base64 (así lo pasa Kestra)")
    args = a.parse_args()
    if args.accion == "entrenar":
        entrenar(args.paso, args.motivo, args.ensayo)
    else:
        import base64
        motivo = base64.b64decode(args.motivo_b64).decode("utf-8") if args.motivo_b64 else args.motivo
        decidir(args.paso, args.aprobar == "true", motivo)
