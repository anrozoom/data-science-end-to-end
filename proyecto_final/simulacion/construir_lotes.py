"""Construye los 26 lotes semanales de la simulación de producción, con la deriva inducida (D1 y D2).

Fuente: la partición de prueba (jul-dic 2020) del snapshot de la OBT (equivalente verificado a
CENTINELA.OBT.TRANSACCIONES_OBT; docs/obt_huella_referencia.json). Ningún dato de prueba se usó para
entrenar ni para elegir umbrales.

Alteraciones (semilla del lote k = 1000 + k; primero D1 y luego D2, con el mismo generador):
  D1 (lotes >= 10, deriva de datos): cada legítima de una categoría presencial se conserva con
     probabilidad 0,30 (se quita ~70 %). Los fraudes se conservan todos -> la prevalencia SUBE.
  D2 (lotes >= 14, deriva conceptual): cada fraude se camufla con probabilidad 0,50:
       amt            <- un monto legítimo de su misma categoría, al azar, del ENTRENAMIENTO
       hora           <- entero al azar entre 9 y 17;  es_nocturna <- False
       monto_relativo <- amt / monto_medio_previo (mismo historial, monto nuevo)
     No se tocan is_fraud, categoría, distancia ni las variables de ráfaga (n_tx_*, gasto_*,
     segundos_desde_anterior). Limitación: el historial de las transacciones POSTERIORES no se recalcula.

Tablas (CENTINELA.PRODUCCION):
  LOTES          entradas del modelo por lote (lo que recibe la API) + marcas y valores originales
  TARGETS        is_fraud de cada transacción y el paso en que "llega" (lote + 2); la simulación lo
                 copia a TARGETS_LLEGADOS cuando llega su paso
  LOTES_RESUMEN  filas, fraudes, prevalencia y alteraciones por lote
  SIMULACION     instante de inicio (UTC) de la simulación vigente: las predicciones, el monitoreo y los
                 reentrenamientos de la simulación son los posteriores a ese instante
  TARGETS_LLEGADOS se vacía (es derivada: la llenan los pasos de la simulación)
Además: docs/simulacion/lotes.csv.

Uso, desde proyecto_final/:  python simulacion/construir_lotes.py [--reemplazar]
Sin --reemplazar se detiene si las tablas ya existen (no reescribe una simulación en curso).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from datos import cargar_obt, metadatos_snapshot  # noqa: E402
from pipeline import dividir  # noqa: E402
from produccion import (COLUMNAS_MODELO, D1_CONSERVA, D1_DESDE, D2_DESDE, D2_FRACCION, D2_HORAS, HORIZONTE,  # noqa: E402
                        N_LOTES, PRESENCIAL, SEMILLA_LOTE, Snowflake, lote_de)


def alterar_lote(k: int, lote: pd.DataFrame, montos_legitimos: dict) -> tuple[pd.DataFrame, dict]:
    """Aplica D1 y D2 al lote k. Devuelve el lote servido (con marcas) y el detalle de lo alterado."""
    rng = np.random.default_rng(SEMILLA_LOTE + k)
    L = lote.copy()
    L["amt_original"], L["hora_original"] = L["amt"], L["hora"]
    L["monto_relativo_original"] = L["monto_relativo"]
    L["alterada_d2"] = False
    info = {"lote": k, "filas_originales": len(L), "fraudes_originales": int(L["is_fraud"].sum()),
            "d1_activa": k >= D1_DESDE, "d2_activa": k >= D2_DESDE, "d1_legitimas_quitadas": 0, "d2_fraudes_camuflados": 0}
    if k >= D1_DESDE:
        quitar = (L["categoria"].isin(PRESENCIAL).to_numpy() & (L["is_fraud"].to_numpy() == 0)
                  & (rng.random(len(L)) > D1_CONSERVA))
        info["d1_legitimas_quitadas"] = int(quitar.sum())
        L = L[~quitar].copy()
    if k >= D2_DESDE:
        fraudes = np.where(L["is_fraud"].to_numpy() == 1)[0]
        sel = fraudes[rng.random(len(fraudes)) < D2_FRACCION]
        col = L.columns.get_loc
        L.iloc[sel, col("amt")] = [rng.choice(montos_legitimos[c]) for c in L["categoria"].to_numpy()[sel]]
        L.iloc[sel, col("hora")] = rng.integers(D2_HORAS[0], D2_HORAS[1] + 1, len(sel)).astype(L["hora"].dtype)
        L.iloc[sel, col("es_nocturna")] = False
        L.iloc[sel, col("alterada_d2")] = True
        L["monto_relativo"] = np.where(L["alterada_d2"], L["amt"] / L["monto_medio_previo"], L["monto_relativo"])
        info["d2_fraudes_camuflados"] = int(len(sel))
    info.update({"filas": len(L), "fraudes": int(L["is_fraud"].sum()),
                 "prevalencia_original_pct": 100 * info["fraudes_originales"] / info["filas_originales"],
                 "prevalencia_pct": 100 * L["is_fraud"].mean()})
    return L, info


def construir() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = cargar_obt()
    Xe, ye, _, _, ent, pru = dividir(df)
    montos_legitimos = {c: Xe.loc[(Xe["categoria"] == c) & (ye == 0), "amt"].to_numpy() for c in Xe["categoria"].unique()}
    pru = pru.assign(lote=lote_de(pru["trans_ts"]))
    lotes, resumen = [], []
    for k in range(N_LOTES):
        g = pru.loc[pru["lote"] == k, ["trans_num", "trans_ts", "lote", "is_fraud"] + COLUMNAS_MODELO]
        L, info = alterar_lote(k, g, montos_legitimos)
        info.update({"desde": g["trans_ts"].min().date(), "hasta": g["trans_ts"].max().date(),
                     "paso_llegada_target": k + HORIZONTE})
        lotes.append(L)
        resumen.append(info)
    return pd.concat(lotes, ignore_index=True), pd.DataFrame(resumen)


def main(reemplazar: bool) -> None:
    lotes, resumen = construir()
    cols = ["lote", "desde", "hasta", "filas_originales", "fraudes_originales", "prevalencia_original_pct",
            "d1_activa", "d1_legitimas_quitadas", "d2_activa", "d2_fraudes_camuflados", "filas", "fraudes",
            "prevalencia_pct", "paso_llegada_target"]
    resumen = resumen[cols]
    salida = RAIZ / "docs" / "simulacion"
    salida.mkdir(parents=True, exist_ok=True)
    resumen.round(4).to_csv(salida / "lotes.csv", index=False)
    print(resumen.round(3).to_string(index=False))

    sf = Snowflake()
    tablas = ("LOTES", "TARGETS", "LOTES_RESUMEN")
    existentes = [t for t in tablas if sf.existe(t)]
    if existentes and not reemplazar:
        sys.exit(f"Ya existen {existentes} en PRODUCCION. Usa --reemplazar para reconstruirlas (reinicia la simulación).")
    entradas = lotes.drop(columns=["is_fraud"])
    entradas["datos_sha256"] = metadatos_snapshot()["sha256"]
    n1 = sf.escribir(entradas, "LOTES", sobrescribir=True)
    targets = lotes[["trans_num", "lote", "is_fraud"]].assign(paso_disponible=lotes["lote"] + HORIZONTE)
    n2 = sf.escribir(targets, "TARGETS", sobrescribir=True)
    n3 = sf.escribir(resumen.assign(desde=pd.to_datetime(resumen["desde"]), hasta=pd.to_datetime(resumen["hasta"])),
                     "LOTES_RESUMEN", sobrescribir=True)
    sf.ejecutar("CREATE TABLE IF NOT EXISTS PRODUCCION.SIMULACION (INICIO_UTC TIMESTAMP_NTZ, DATOS_SHA256 VARCHAR, LOTES NUMBER)")
    sf.ejecutar(f"INSERT INTO PRODUCCION.SIMULACION SELECT SYSDATE(), '{entradas['datos_sha256'].iloc[0]}', {len(resumen)}")
    if sf.existe("TARGETS_LLEGADOS"):
        sf.ejecutar("TRUNCATE TABLE PRODUCCION.TARGETS_LLEGADOS")
    print(f"PRODUCCION.LOTES {n1} filas | TARGETS {n2} | LOTES_RESUMEN {n3}")
    sf.cerrar()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--reemplazar", action="store_true")
    main(p.parse_args().reemplazar)
