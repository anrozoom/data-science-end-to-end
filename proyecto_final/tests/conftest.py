"""Configuración común de las pruebas: la API se carga con el modelo del fixture (sin servidor de MLflow)
y sin registrar en Snowflake, así que corren igual en el Codespace y en GitHub Actions."""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
FIX = RAIZ / "tests" / "fixtures"

os.environ["MODELO_URI"] = str(FIX / "modelo_champion")
os.environ["REGISTRO_SNOWFLAKE"] = "false"
os.environ["ADMIN_TOKEN"] = "token-de-prueba"
os.environ["RECARGA_SEGUNDOS"] = "3600"
os.environ["MODO_RESPALDO"] = "false"
sys.path.insert(0, str(RAIZ / "api"))

COLUMNAS_ENTRADA = None


@pytest.fixture(scope="session")
def muestra() -> pd.DataFrame:
    return pd.read_parquet(FIX / "muestra_prueba.parquet")


@pytest.fixture(scope="session")
def esperadas() -> dict:
    return json.loads((FIX / "metricas_esperadas.json").read_text())


@pytest.fixture(scope="session")
def api():
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as cliente:
        yield cliente


@pytest.fixture(scope="session")
def modelo():
    import mlflow
    return mlflow.sklearn.load_model(str(FIX / "modelo_champion"))


def a_json(fila: pd.Series) -> dict:
    """Una fila de la muestra como cuerpo de /predecir (sin el target ni la probabilidad esperada)."""
    d = fila.drop(labels=["is_fraud", "probabilidad_esperada"]).to_dict()
    return {k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v)) for k, v in d.items()}
