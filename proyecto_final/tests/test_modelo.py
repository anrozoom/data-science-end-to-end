"""El modelo exportado reproduce la métrica registrada en MLflow sobre la muestra fija del repositorio.

Métrica: AUC-PR en tests/fixtures/muestra_prueba.parquet (todos los fraudes de la prueba + 8.000 legítimas,
semilla 42), registrada en la corrida del champion como ci_muestra_auc_pr. Es más alta que la AUC-PR de la
prueba completa (0,9655) porque la muestra tiene ~20 % de fraude y no 0,38 %: lo que se compara es la misma
métrica sobre la misma muestra.

Tolerancia 1e-9: la predicción de HistGradientBoosting es determinista; la única diferencia esperable entre
máquinas (Codespace frente a GitHub Actions) es de redondeo de punto flotante, del orden de 1e-15. Un cambio
real del modelo o de la preparación mueve la AUC-PR mucho más que 1e-9.
"""
import numpy as np
import pytest
from sklearn.metrics import average_precision_score

COLUMNAS = None
TOLERANCIA = 1e-9


def test_reproduce_la_auc_pr_registrada(modelo, muestra, esperadas):
    X = muestra.drop(columns=["trans_num", "is_fraud", "probabilidad_esperada"])
    auc = average_precision_score(muestra["is_fraud"], modelo.predict_proba(X)[:, 1])
    assert auc == pytest.approx(esperadas["auc_pr_muestra"], abs=TOLERANCIA)


def test_reproduce_cada_probabilidad(modelo, muestra):
    X = muestra.drop(columns=["trans_num", "is_fraud", "probabilidad_esperada"])
    assert np.max(np.abs(modelo.predict_proba(X)[:, 1] - muestra["probabilidad_esperada"].to_numpy())) < TOLERANCIA


def test_la_api_usa_el_mismo_modelo(api, muestra):
    from conftest import a_json
    fila = muestra.iloc[3]
    assert api.post("/predecir", json=a_json(fila)).json()["probabilidad"] == pytest.approx(fila["probabilidad_esperada"], abs=TOLERANCIA)
