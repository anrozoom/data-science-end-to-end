"""Comportamiento de negocio del modelo, sobre la muestra fija de la prueba (tests/fixtures).

Cada prueba cambia UNA cosa de transacciones reales, manteniendo el resto del perfil, y exige que la
probabilidad no baje en la gran mayoría de los casos y que suba en promedio. Se mide sobre todos los
casos de la muestra porque HistGradientBoosting no es monótono por construcción: exigir el 100 % fila por
fila sería falso para cualquier árbol; lo que importa al negocio es la tendencia y su alcance.

  B2  Una compra nocturna (23:00) no es menos riesgosa que la misma compra a las 14:00.
  B5  Un monto alto PARA SU CATEGORÍA (1,5 × p95) no es menos riesgoso que uno típico (0,5 × p95).
  B1  (falla conocida, xfail) Un monto MUY por encima del p95 de su categoría (5 ×) no baja la probabilidad.
      El modelo NO lo cumple: en Sparkov el fraude más caro del entrenamiento es de USD 1.376 y ninguna de
      las 780 transacciones con monto > 5 × p95 es fraude, así que aprendió "monto altísimo = legítima".
      Se documenta en docs/cambios.md y en los criterios de retirada; no se maquilla.
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
