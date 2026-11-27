"""Comportamiento de negocio del modelo, sobre la muestra fija de la prueba (tests/fixtures).

Cada prueba cambia UNA cosa de transacciones reales, manteniendo el resto del perfil, y exige que la
probabilidad no baje en la gran mayoría de los perfiles y que suba en promedio.

Los mínimos son una TOLERANCIA DE NEGOCIO, no el valor medido: un HistGradientBoosting no es monótono por
construcción (cada árbol parte el espacio en tramos), así que exigir el 100 % fila por fila sería falso
para cualquier modelo de árboles. El negocio acepta que una fracción pequeña de perfiles se comporte al
revés, siempre que la tendencia sea la esperada; esas excepciones se revisan caso por caso.
  - B2 >= 95 %: la hora es una señal fuerte y estable del dominio (2,08 % de fraude de noche frente a
    0,11 % de día en entrenamiento); se tolera como máximo 1 perfil de cada 20 al revés.
  - B5 >= 90 %: el monto interactúa con la categoría, el canal y el historial, y el fraude de Sparkov se
    concentra en una banda de montos; se tolera como máximo 1 perfil de cada 10 al revés.
Valores medidos en la muestra fija (2026-11-27): B2 97,5 % (Δ medio +0,032), B5 94,8 % (Δ medio +0,154).

  B2  Una compra nocturna (23:00) no es menos riesgosa que la misma compra a las 14:00.
  B5  Un monto alto PARA SU CATEGORÍA (1,5 × p95) no es menos riesgoso que uno típico (0,5 × p95).
  B1  (falla conocida, xfail estricto) Un monto MUY por encima del p95 de su categoría (5 ×) no baja la
      probabilidad. El modelo NO lo cumple: baja en el 90,8 % de los fraudes (mediana −0,021) y la decisión
      empeora en el 22,6 %. En Sparkov el fraude más caro del entrenamiento es de USD 1.376 y ninguna de
      las 780 transacciones con monto > 5 × p95 es fraude. Ver docs/hallazgos/monto_fuera_de_soporte.md.
"""
import json
from pathlib import Path

import numpy as np
import pytest

CATALOGOS = json.loads((Path(__file__).resolve().parents[1] / "api" / "catalogos.json").read_text())
MIN_CUMPLE_B2, MIN_CUMPLE_B5 = 0.95, 0.90


def _x(muestra):
    return muestra.drop(columns=["trans_num", "is_fraud", "probabilidad_esperada"])


def _con_monto(X, factor):
    Y = X.copy()
    p95 = X["categoria"].map(CATALOGOS["p95_amt_por_categoria"]).astype(float)
    Y["amt"] = factor * p95
    Y["monto_relativo"] = Y["amt"] / X["monto_medio_previo"]        # mismo historial, monto nuevo
    return Y


def _proporcion_que_no_baja(antes, despues):
    d = despues - antes
    return float((d >= -1e-12).mean()), float(d.mean())


def test_b2_compra_nocturna_no_es_menos_riesgosa_que_diurna(modelo, muestra):
    X = _x(muestra)
    dia, noche = X.copy(), X.copy()
    dia["hora"], dia["es_nocturna"] = 14, False
    noche["hora"], noche["es_nocturna"] = 23, True
    cumple, delta = _proporcion_que_no_baja(modelo.predict_proba(dia)[:, 1], modelo.predict_proba(noche)[:, 1])
    print(f"B2: {cumple:.2%} no baja; Δ medio {delta:+.4f}")
    assert cumple >= MIN_CUMPLE_B2 and delta > 0


def test_b5_monto_alto_para_su_categoria_no_es_menos_riesgoso(modelo, muestra):
    X = _x(muestra)
    cumple, delta = _proporcion_que_no_baja(modelo.predict_proba(_con_monto(X, 0.5))[:, 1],
                                            modelo.predict_proba(_con_monto(X, 1.5))[:, 1])
    print(f"B5: {cumple:.2%} no baja; Δ medio {delta:+.4f}")
    assert cumple >= MIN_CUMPLE_B5 and delta > 0


@pytest.mark.xfail(strict=True, reason="Falla conocida del modelo (datos simulados): montos > 5×p95 nunca son "
                                        "fraude en Sparkov. Ver docs/cambios.md y criterios de retirada.")
def test_b1_monto_muy_por_encima_del_p95_no_baja_la_probabilidad(modelo, muestra):
    X = _x(muestra)
    fr = muestra["is_fraud"].to_numpy() == 1
    antes = modelo.predict_proba(X)[:, 1]
    alto = X.copy()
    p95 = X["categoria"].map(CATALOGOS["p95_amt_por_categoria"]).astype(float)
    alto["amt"] = np.maximum(X["amt"], 5 * p95)
    alto["monto_relativo"] = alto["amt"] / X["monto_medio_previo"]
    cumple, _ = _proporcion_que_no_baja(antes[fr], modelo.predict_proba(alto)[:, 1][fr])
    print(f"B1 (fraudes): {cumple:.2%} no baja")
    assert cumple >= MIN_CUMPLE_B2
