"""Atajo para preparar una cuenta de Snowflake nueva para las demostraciones, SIN volver a correr la simulación.

Copia de PRODUCCION.TARGETS a PRODUCCION.TARGETS_LLEGADOS el target de los lotes 0..HASTA, con el paso en que
habría llegado (lote + 2). Es lo que la simulación completa hace paso a paso (simulacion/ejecutar_paso.py), sin
las predicciones ni el monitoreo de cada paso. Lo necesita la demostración de reentrenamiento
(scripts/demo_reentrenamiento.sh), que entrena con los lotes etiquetados 0..20 y evalúa en el 21.

Se usó al pasar a la cuenta de respaldo el 2026-11-28, cuando la cuenta original quedó suspendida
(docs/simulacion/incidentes.md). Los resultados de la simulación completa siguen en docs/ (CSV).

Uso, desde proyecto_final/ (después de simulacion/construir_lotes.py):  python simulacion/cargar_targets_llegados.py [--hasta 23]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "simulacion"))

from ejecutar_paso import DDL_LLEGADOS  # noqa: E402
from produccion import HORIZONTE, N_LOTES, Snowflake  # noqa: E402


def main(hasta: int) -> None:
    hasta = min(hasta, N_LOTES - 1 - HORIZONTE)          # los lotes 24 y 25 no reciben target en la simulación
    sf = Snowflake()
    sf.ejecutar(DDL_LLEGADOS)
    sf.ejecutar(f"DELETE FROM PRODUCCION.TARGETS_LLEGADOS WHERE LOTE <= {hasta}")
    n = sf.ejecutar(f"""INSERT INTO PRODUCCION.TARGETS_LLEGADOS
        SELECT TRANS_NUM, LOTE, IS_FRAUD, LOTE + {HORIZONTE}, SYSDATE() FROM PRODUCCION.TARGETS WHERE LOTE <= {hasta}""")
    r = sf.sql("SELECT COUNT(*) AS n, SUM(IS_FRAUD) AS f, MIN(LOTE) AS l0, MAX(LOTE) AS l1 FROM PRODUCCION.TARGETS_LLEGADOS").iloc[0]
    sf.cerrar()
    print(f"TARGETS_LLEGADOS: {n} filas insertadas; total {int(r.n)} filas, {int(r.f)} fraudes, lotes {int(r.l0)} a {int(r.l1)}")


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--hasta", type=int, default=23)
    main(a.parse_args().hasta)
