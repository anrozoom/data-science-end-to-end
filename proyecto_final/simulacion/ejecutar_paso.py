"""Un paso de la simulación de producción: el lote k pasa por la API y llega el target del lote k - 2.

1. Idempotencia: borra lo que un intento anterior de ESTE paso haya dejado (predicciones y solicitudes con
   LOTE = k registradas DESPUÉS del inicio de la simulación, y la llegada del target del lote k - 2). Las 204
   predicciones de prueba de la fase 2 (anteriores al inicio, algunas con LOTE = 0) nunca se tocan.
2. Lee el lote k de CENTINELA.PRODUCCION.LOTES (Snowflake), en orden cronológico.
3. Tráfico hacia la API: N_ONLINE transacciones al azar (semilla 1000 + k) van una por una a POST /predecir
   (latencia online real); el resto, en bloques de TAMANO_BLOQUE a POST /predecir_lote. Cada transacción se
   predice UNA vez y la API registra cada una como predicción individual (PREDICCIONES) con su id.
4. Espera a que la API termine de escribir en Snowflake (microlotes en segundo plano) y verifica el conteo.
5. Llega el target del lote k - 2: TARGETS -> TARGETS_LLEGADOS (con el paso de llegada).

Uso:  python simulacion/ejecutar_paso.py --paso 0      (API_URL, por defecto http://localhost:8000)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from produccion import FILTRO_SIM, HORIZONTE, SEMILLA_LOTE, Snowflake, emitir_salidas, tipar  # noqa: E402

API = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
N_ONLINE = int(os.environ.get("N_ONLINE", "200"))
TAMANO_BLOQUE = int(os.environ.get("TAMANO_BLOQUE", "2000"))

DDL_LLEGADOS = """CREATE TABLE IF NOT EXISTS PRODUCCION.TARGETS_LLEGADOS (
    TRANS_NUM VARCHAR, LOTE NUMBER, IS_FRAUD NUMBER, PASO_LLEGADA NUMBER, TS_LLEGADA TIMESTAMP_NTZ)"""


def esperar_registro(sf: Snowflake, lote: int, esperadas: int, limite_s: float = 300) -> int:
    fin = time.time() + limite_s
    n = -1
    while time.time() < fin:
        pend = requests.get(f"{API}/salud", timeout=10).json()["registro_snowflake"]["pendientes"]
        if not any(pend.values()):
            n = int(sf.sql(f"SELECT COUNT(*) AS n FROM PRODUCCION.PREDICCIONES WHERE LOTE = {lote} AND {FILTRO_SIM}")["n"].iloc[0])
            if n >= esperadas:
                return n
        time.sleep(3)
    raise RuntimeError(f"La API no registró las {esperadas} predicciones del lote {lote} a tiempo (hay {n})")


def main(paso: int) -> dict:
    t0 = time.time()
    sf = Snowflake()
    if not sf.existe("SIMULACION"):
        raise RuntimeError("Falta PRODUCCION.SIMULACION: ejecuta antes simulacion/construir_lotes.py")
    salud = requests.get(f"{API}/salud", timeout=10).json()
    if not salud["modelo_cargado"]:
        print(f"AVISO: la API está en modo de respaldo ({salud['motivo_respaldo']})")

    # 1 ---- idempotencia del paso
    for tabla in ("PREDICCIONES", "SOLICITUDES"):
        if sf.existe(tabla):
            n = sf.ejecutar(f"DELETE FROM PRODUCCION.{tabla} WHERE LOTE = {paso} AND {FILTRO_SIM}")
            if n:
                print(f"Reintento del paso {paso}: se borraron {n} filas previas de {tabla} (LOTE = {paso})")

    # 2 ---- lote k desde Snowflake
    lote = sf.sql(f"SELECT * FROM PRODUCCION.LOTES WHERE LOTE = {paso} ORDER BY TRANS_TS, TRANS_NUM")
    if lote.empty:
        raise RuntimeError(f"PRODUCCION.LOTES no tiene el lote {paso}")
    X = tipar(lote)
    registros = json.loads(X.to_json(orient="records"))          # NaN -> null, tipos JSON nativos
    for r, t in zip(registros, lote["trans_num"]):
        r["trans_num"] = t
    t_lectura = time.time() - t0

    # 3 ---- tráfico hacia la API
    rng = np.random.default_rng(SEMILLA_LOTE + paso)
    online = set(rng.choice(len(registros), size=min(N_ONLINE, len(registros)), replace=False).tolist())
    decisiones, versiones, respaldo = Counter(), Counter(), 0
    s = requests.Session()
    t1 = time.time()
    for i in sorted(online):
        r = s.post(f"{API}/predecir", params={"lote": paso}, json=registros[i], timeout=30)
        r.raise_for_status()
        p = r.json()
        decisiones[p["decision"]] += 1
        versiones[p["version_modelo"]] += 1
        respaldo += p["respaldo"]
    t_online = time.time() - t1
    resto = [registros[i] for i in range(len(registros)) if i not in online]
    t2 = time.time()
    for ini in range(0, len(resto), TAMANO_BLOQUE):
        r = s.post(f"{API}/predecir_lote", json={"lote": paso, "transacciones": resto[ini:ini + TAMANO_BLOQUE]}, timeout=120)
        r.raise_for_status()
        for p in r.json()["predicciones"]:
            decisiones[p["decision"]] += 1
            versiones[p["version_modelo"]] += 1
            respaldo += p["respaldo"]
    t_bloques = time.time() - t2

    # 4 ---- registro completo en Snowflake
    n_reg = esperar_registro(sf, paso, len(registros))

    # 5 ---- llega el target del lote k - 2
    etiquetado = paso - HORIZONTE
    n_target = 0
    if etiquetado >= 0:
        sf.ejecutar(DDL_LLEGADOS)
        sf.ejecutar(f"DELETE FROM PRODUCCION.TARGETS_LLEGADOS WHERE LOTE = {etiquetado}")
        n_target = sf.ejecutar(f"""INSERT INTO PRODUCCION.TARGETS_LLEGADOS
            SELECT TRANS_NUM, LOTE, IS_FRAUD, {paso}, SYSDATE()
            FROM PRODUCCION.TARGETS WHERE LOTE = {etiquetado}""")
    sf.cerrar()

    res = {"paso": paso, "lote": paso, "filas": len(registros), "online": len(online), "en_bloques": len(resto),
           "registradas": n_reg, "decisiones": dict(decisiones), "versiones": dict(versiones), "respaldo": respaldo,
           "lote_etiquetado": etiquetado if etiquetado >= 0 else None, "targets_llegados": n_target,
           "segundos": {"lectura": round(t_lectura, 1), "online": round(t_online, 1), "bloques": round(t_bloques, 1),
                        "total": round(time.time() - t0, 1)}}
    print(json.dumps(res, ensure_ascii=False))
    emitir_salidas(**{k: v for k, v in res.items() if k != "segundos"}, segundos_total=res["segundos"]["total"],
                   version=max(versiones, key=versiones.get) if versiones else None)
    return res


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--paso", type=int, required=True)
    main(a.parse_args().paso)
