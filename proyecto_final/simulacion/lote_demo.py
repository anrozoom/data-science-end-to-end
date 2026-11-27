"""Lote de demostración con deriva para el video (scripts/demo_deriva.sh).

Lote 100 = las transacciones ORIGINALES del lote 15 (2020-10-14 a 2020-10-20) con D1 y D2 aplicadas con la
semilla 1000 + 100 (simulacion/construir_lotes.py). Se escribe en PRODUCCION.LOTES y TARGETS con LOTE = 100
(idempotente: borra antes el lote 100). Los pasos y lotes >= 100 son demostraciones y quedan fuera de todos
los resúmenes y exportes de la simulación.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "simulacion"))

from construir_lotes import alterar_lote  # noqa: E402
from datos import cargar_obt, metadatos_snapshot  # noqa: E402
from pipeline import dividir  # noqa: E402
from produccion import COLUMNAS_MODELO, HORIZONTE, PASO_DEMO, Snowflake, lote_de  # noqa: E402

LOTE_BASE = 15


def main() -> None:
    Xe, ye, _, _, _, pru = dividir(cargar_obt())
    montos = {c: Xe.loc[(Xe["categoria"] == c) & (ye == 0), "amt"].to_numpy() for c in Xe["categoria"].unique()}
    g = pru[lote_de(pru["trans_ts"]) == LOTE_BASE][["trans_num", "trans_ts", "is_fraud"] + COLUMNAS_MODELO].assign(lote=PASO_DEMO)
    L, info = alterar_lote(PASO_DEMO, g, montos)
    sf = Snowflake()
    for t in ("LOTES", "TARGETS"):
        sf.ejecutar(f"DELETE FROM PRODUCCION.{t} WHERE LOTE = {PASO_DEMO}")
    sf.escribir(L.drop(columns=["is_fraud"]).assign(datos_sha256=metadatos_snapshot()["sha256"]), "LOTES")
    sf.escribir(L[["trans_num", "lote", "is_fraud"]].assign(paso_disponible=PASO_DEMO + HORIZONTE), "TARGETS")
    sf.cerrar()
    print(f"Lote de demostración {PASO_DEMO} (base: lote {LOTE_BASE}): {info['filas']} filas, "
          f"{info['d1_legitimas_quitadas']} legítimas presenciales quitadas (D1), {info['d2_fraudes_camuflados']} fraudes camuflados (D2)")


if __name__ == "__main__":
    main()
