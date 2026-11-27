"""Monitoreo de un paso de la simulación (lo llama kestra/monitoreo.yml después de cada lote).

Paso k:
  sistema  (lote k)      latencia p50/p95 de /predecir y por transacción en /predecir_lote, 4xx, 5xx, volumen
                         frente a la misma semana de 2019
  modelo   (lote k)      distribución de la probabilidad, tasa de cada decisión, tasa de alertas, respaldo
  datos    (lote k)      nulos, fuera del soporte de entrenamiento, categorías no vistas, PSI por variable
                         (+ KS / chi-cuadrado) frente a la misma semana de 2019
  desempeño (lote k - 2) llegó su target: AUC-PR, pérdida neta (USD y por 1.000), recall, precisión, y las
                         pérdidas de las reglas fijas y de no hacer nada en el mismo lote
Disparo de reentrenamiento (diseño aprobado):
  desempeño  los 2 lotes etiquetados más recientes, servidos por el champion VIGENTE y posteriores al último
             lote usado en una decisión, tienen AUC-PR < umbral (CV del PSet 3 a escala semanal)
  calendario pasos 12 y 24, si no hubo una decisión en los 4 pasos anteriores
Escribe PRODUCCION.MONITOREO (formato largo) y PRODUCCION.ALERTAS (idempotente por paso) y devuelve a
Kestra: disparo, número de alertas y su resumen.

Uso:  python monitoreo/monitorear.py --paso 5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "monitoreo"))

import alertas as catalogo  # noqa: E402
from datos import cargar_obt  # noqa: E402
from deriva import NUMERICAS, VIGILADAS, referencia_misma_semana, tabla_psi  # noqa: E402
from pipeline import COSTO_FALSA_ALARMA, auc_pr, dividir  # noqa: E402
from produccion import (CATALOGOS, FILTRO_SIM, HORIZONTE, INICIO_SIM_SQL, N_LOTES, NOMBRE_MODELO, PASOS_CALENDARIO,  # noqa: E402
                        Snowflake, configurar_mlflow, emitir_salidas, umbrales)


def reglas_fijas(X: pd.DataFrame) -> np.ndarray:
    """Las reglas actuales del banco (PSet 1), igual que el respaldo de la API."""
    p95 = X["categoria"].map(CATALOGOS["p95_amt_por_categoria"]).astype(float).fillna(np.inf)
    return ((X["amt"] > p95) | (X["es_nocturna"].astype(bool) & (X["amt"] >= CATALOGOS["regla_monto_minimo_nocturno"]))
            | (X["distancia_km"] > CATALOGOS["regla_distancia_km"])).to_numpy()


def perdida(y, alerta, monto) -> float:
    return float(monto[(y == 1) & ~alerta].sum() + COSTO_FALSA_ALARMA * ((y == 0) & alerta).sum())


def predicciones(sf: Snowflake, lote: int) -> pd.DataFrame:
    p = sf.sql(f"""SELECT TRANS_NUM, ENTRADAS, PROBABILIDAD, DECISION, MODELO_VERSION, RESPALDO, UMBRAL_VERIFICAR
                   FROM PRODUCCION.PREDICCIONES WHERE LOTE = {lote} AND {FILTRO_SIM}""")
    if p.empty:
        return p
    X = pd.DataFrame([json.loads(e) for e in p["entradas"]])
    return pd.concat([p.drop(columns=["entradas"]).reset_index(drop=True), X], axis=1)


def metricas_etiquetado(sf: Snowflake, lote: int, u1: float) -> dict | None:
    p = predicciones(sf, lote)
    t = sf.sql(f"SELECT TRANS_NUM, IS_FRAUD FROM PRODUCCION.TARGETS_LLEGADOS WHERE LOTE = {lote}")
    if p.empty or t.empty:
        return None
    d = p.merge(t, on="trans_num", how="inner", validate="one_to_one")
    y, monto = d["is_fraud"].to_numpy().astype(int), d["amt"].to_numpy(dtype=float)
    alerta = d["decision"].isin(["verificar", "retener"]).to_numpy()
    con_prob = d["probabilidad"].notna().to_numpy()
    reglas = reglas_fijas(d)
    versiones = d["modelo_version"].value_counts()
    return {"lote": lote, "filas": len(d), "fraudes": int(y.sum()), "prevalencia": float(y.mean()),
            "version": str(versiones.index[0]), "versiones": versiones.to_dict(),
            "auc_pr": auc_pr(y[con_prob], d["probabilidad"].to_numpy()[con_prob]) if y[con_prob].sum() and con_prob.all() else None,
            "perdida_neta": perdida(y, alerta, monto), "perdida_x1000": 1000 * perdida(y, alerta, monto) / len(d),
            "fraude_no_detectado_usd": float(monto[(y == 1) & ~alerta].sum()), "falsas_alarmas": int(((y == 0) & alerta).sum()),
            "recall": float(alerta[y == 1].mean()) if y.sum() else None,
            "precision_alertas": float(y[alerta].mean()) if alerta.any() else None,
            "perdida_reglas": perdida(y, reglas, monto), "perdida_sin_modelo": float(monto[y == 1].sum())}


def disparo(sf: Snowflake, paso: int, historial: pd.DataFrame, version_champion: str, umbral: float) -> dict:
    ultima = {"paso": None, "lote_evaluacion": -1}
    if sf.existe("REENTRENAMIENTOS"):
        r = sf.sql(f"SELECT MAX(PASO) AS paso, MAX(LOTE_EVALUACION) AS lote FROM PRODUCCION.REENTRENAMIENTOS "
                   f"WHERE INICIO_SIMULACION = {INICIO_SIM_SQL} AND PASO < {N_LOTES}")   # sin las demostraciones
        if not r.empty and pd.notna(r["paso"].iloc[0]):
            ultima = {"paso": int(r["paso"].iloc[0]), "lote_evaluacion": int(r["lote"].iloc[0])}
    res = {"motivo": "ninguno", "lotes": [], "auc_lotes": [], "version": version_champion, "ultima_decision": ultima}
    h = historial.sort_values("lote")
    if len(h) >= 2:
        dos = h.tail(2)
        if (list(dos["lote"]) == [dos["lote"].iloc[1] - 1, dos["lote"].iloc[1]]
                and (dos["version"].astype(str) == version_champion).all() and (dos["lote"] > ultima["lote_evaluacion"]).all()
                and (dos["auc_pr"] < umbral).all()):
            res.update(motivo="desempeño", lotes=dos["lote"].astype(int).tolist(), auc_lotes=dos["auc_pr"].astype(float).tolist())
            return res
    if paso in PASOS_CALENDARIO and (ultima["paso"] is None or paso - ultima["paso"] >= 4):
        res["motivo"] = "calendario"
    return res


def main(paso: int) -> dict:
    t0 = time.time()
    u = umbrales()
    u1 = u["umbral_verificar_u1"]
    sf = Snowflake()
    inicio = sf.sql(f"SELECT {INICIO_SIM_SQL} AS i")["i"].iloc[0]

    # ---- lote k: sistema, modelo y datos
    p = predicciones(sf, paso)
    if p.empty:
        raise RuntimeError(f"No hay predicciones del lote {paso} en esta simulación")
    sol = sf.sql(f"SELECT RUTA, CODIGO_HTTP, LATENCIA_MS, N_PREDICCIONES FROM PRODUCCION.SOLICITUDES WHERE LOTE = {paso} AND {FILTRO_SIM}")
    df = cargar_obt()
    _, _, _, _, ent, _ = dividir(df)
    lote_ts = sf.sql(f"SELECT MIN(TRANS_TS) AS d, MAX(TRANS_TS) AS h FROM PRODUCCION.LOTES WHERE LOTE = {paso}")
    ref = referencia_misma_semana(ent, pd.Timestamp(lote_ts["d"].iloc[0]), pd.Timestamp(lote_ts["h"].iloc[0]))
    onl = sol[sol["ruta"] == "/predecir"]["latencia_ms"]
    blq = sol[sol["ruta"] == "/predecir_lote"]
    sistema = {"solicitudes": int(len(sol)), "errores_4xx": int(sol["codigo_http"].between(400, 499).sum()),
               "errores_5xx": int((sol["codigo_http"] >= 500).sum()),
               "latencia_online_p50_ms": float(onl.quantile(.5)) if len(onl) else None,
               "latencia_online_p95_ms": float(onl.quantile(.95)) if len(onl) else None,
               "latencia_lote_ms_por_tx": float(blq["latencia_ms"].sum() / max(blq["n_predicciones"].sum(), 1)) if len(blq) else None,
               "volumen": int(len(p)), "volumen_2019": int(len(ref)), "volumen_relativo_2019": len(p) / len(ref) if len(ref) else None}
    prob = p["probabilidad"].astype(float)
    dec = p["decision"].value_counts(normalize=True)
    modelo = {"version": str(p["modelo_version"].mode().iloc[0]), "respaldo_pct": 100 * float(p["respaldo"].astype(bool).mean()),
              "prob_media": float(prob.mean()), "prob_p50": float(prob.quantile(.5)), "prob_p95": float(prob.quantile(.95)),
              "prob_p99": float(prob.quantile(.99)), **{f"tasa_{k}": float(dec.get(k, 0.0)) for k in ("aprobar", "verificar", "retener")}}
    modelo["tasa_alertas"] = modelo["tasa_verificar"] + modelo["tasa_retener"]
    psi = tabla_psi(ref, p)
    datos = {"nulos_pct": {v: 100 * float(p[v].isna().mean()) for v in NUMERICAS},
             "fuera_de_soporte_pct": {v: 100 * float(((p[v] < a) | (p[v] > b)).mean()) for v, (a, b) in u["soporte"].items()},
             "categorias_no_vistas": int(sum((~p[c].isin(CATALOGOS[c])).sum() for c in ("categoria", "canal", "state"))),
             "psi": psi.to_dict(orient="records")}

    # ---- lote k - 2: llegó su target
    etiquetado = metricas_etiquetado(sf, paso - HORIZONTE, u1) if paso >= HORIZONTE else None

    # ---- historial de desempeño de esta simulación (lotes etiquetados anteriores + el de hoy)
    hist = pd.DataFrame(columns=["lote", "auc_pr", "version"])
    if sf.existe("MONITOREO"):
        hist = sf.sql(f"""SELECT LOTE, VALOR AS auc_pr, MODELO_VERSION AS version FROM PRODUCCION.MONITOREO
                          WHERE INICIO_SIMULACION = {INICIO_SIM_SQL} AND GRUPO = 'desempeño' AND METRICA = 'auc_pr'
                          AND PASO < {min(paso, N_LOTES)}""")
    if etiquetado and etiquetado["auc_pr"] is not None:
        hist = pd.concat([hist, pd.DataFrame([{"lote": etiquetado["lote"], "auc_pr": etiquetado["auc_pr"],
                                              "version": etiquetado["version"]}])], ignore_index=True)
    configurar_mlflow()
    from mlflow import MlflowClient
    version_champion = MlflowClient().get_model_version_by_alias(NOMBRE_MODELO, "champion").version
    disp = disparo(sf, paso, hist, str(version_champion), u["desempeno"]["umbral_auc_pr"])

    m = {"sistema": sistema, "modelo": modelo, "datos": datos, "etiquetado": etiquetado, "disparo": disp}
    alertas = catalogo.evaluar(m, u)

    # ---- MONITOREO (formato largo) y ALERTAS, idempotentes por paso
    ts = pd.Timestamp.utcnow().tz_localize(None)
    filas = []

    def fila(grupo, metrica, valor, lote=paso, variable=None, umbral=None, estado=None, version=modelo["version"]):
        if valor is None:
            return
        filas.append({"inicio_simulacion": inicio, "paso": paso, "lote": lote, "grupo": grupo, "metrica": metrica,
                      "variable": variable, "valor": float(valor), "umbral": None if umbral is None else float(umbral),
                      "estado": estado, "modelo_version": str(version), "ts_utc": ts})

    for k, v in sistema.items():
        fila("sistema", k, v)
    for k, v in modelo.items():
        if k != "version":
            fila("modelo", k, v)
    for v, x in datos["nulos_pct"].items():
        fila("datos", "nulos_pct", x, variable=v)
    for v, x in datos["fuera_de_soporte_pct"].items():
        fila("datos", "fuera_de_soporte_pct", x, variable=v, umbral=100 * u["datos"]["fuera_de_soporte_max"])
    fila("datos", "categorias_no_vistas", datos["categorias_no_vistas"], umbral=0)
    for f in datos["psi"]:
        fila("datos", "psi", f["psi"], variable=f["variable"], umbral=u["psi"]["alerta"], estado=f["estado"])
        fila("datos", f"{f['prueba']}_estadistico", f["estadistico"], variable=f["variable"])
        fila("datos", f"{f['prueba']}_valor_p", f["valor_p"], variable=f["variable"])
    if etiquetado:
        e = etiquetado
        for k in ("filas", "fraudes", "prevalencia", "auc_pr", "perdida_neta", "perdida_x1000", "fraude_no_detectado_usd",
                  "falsas_alarmas", "recall", "precision_alertas", "perdida_reglas", "perdida_sin_modelo"):
            umbral = u["desempeno"]["umbral_auc_pr"] if k == "auc_pr" else None
            estado = None if k != "auc_pr" or e[k] is None else ("alerta" if e[k] < umbral else "ok")
            fila("desempeño", k, e[k], lote=e["lote"], umbral=umbral, estado=estado, version=e["version"])
    mon = pd.DataFrame(filas)
    al = pd.DataFrame(alertas).assign(inicio_simulacion=inicio, paso=paso, lote=paso, ts_utc=ts) if alertas else pd.DataFrame()
    if not al.empty:
        lote_al = {"MOD-DES-1": paso - HORIZONTE, "MOD-PERD": paso - HORIZONTE, "MOD-DES-2": paso - HORIZONTE}
        al["lote"] = [lote_al.get(i, paso) for i in al["id_alerta"]]
    for tabla, d in (("MONITOREO", mon), ("ALERTAS", al)):
        if sf.existe(tabla):
            sf.ejecutar(f"DELETE FROM PRODUCCION.{tabla} WHERE PASO = {paso} AND INICIO_SIMULACION = {INICIO_SIM_SQL}")
        if not d.empty:
            sf.escribir(d, tabla)
    sf.cerrar()

    # ---- log legible y salidas para Kestra
    print(f"PASO {paso} | lote {paso}: {sistema['volumen']} transacciones ({sistema['volumen_relativo_2019']:.2f} de 2019), "
          f"p95 /predecir {sistema['latencia_online_p95_ms']:.1f} ms, 4xx {sistema['errores_4xx']}, 5xx {sistema['errores_5xx']}, "
          f"alertas {modelo['tasa_alertas']:.2%}, versión {modelo['version']}")
    print("PSI máx: " + ", ".join(f"{r['variable']} {r['psi']:.3f}" for r in sorted(datos["psi"], key=lambda r: -r["psi"])[:3]))
    if etiquetado:
        e = etiquetado
        print(f"Target del lote {e['lote']} (v{e['version']}): AUC-PR {e['auc_pr'] if e['auc_pr'] is None else round(e['auc_pr'], 4)}, "
              f"pérdida {e['perdida_neta']:.0f} USD ({e['perdida_x1000']:.2f} por 1.000) | reglas {e['perdida_reglas']:.0f} | "
              f"sin modelo {e['perdida_sin_modelo']:.0f}; prevalencia {e['prevalencia']:.3%}")
    for a in sorted(alertas, key=lambda a: catalogo.SEVERIDADES.index(a["severidad"])):
        print("ALERTA " + a["mensaje"])
    print(f"Disparo de reentrenamiento: {disp['motivo']} (champion v{version_champion}; {time.time() - t0:.0f} s)")
    graves = [a for a in alertas if a["severidad"] in ("crítica", "alta", "media")]
    emitir_salidas(paso=paso, disparo=disp["motivo"], n_alertas=len(alertas), n_alertas_graves=len(graves),
                   resumen_alertas=" || ".join(a["mensaje"] for a in graves) or "sin alertas (media o mayor)",
                   version_champion=str(version_champion))
    return m


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--paso", type=int, required=True)
    main(a.parse_args().paso)
