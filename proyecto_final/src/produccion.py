"""Constantes y utilidades compartidas de la simulación de producción, el monitoreo y el reentrenamiento.

Diseño aprobado (docs/simulacion/diseno_deriva.md):
  - 26 lotes semanales de la partición de prueba (jul-dic 2020) desde el 2020-07-01; el lote 25 junta los
    últimos 9 días. El target (confirmación del fraude) de un lote llega HORIZONTE = 2 pasos después.
  - D1, deriva de datos (P(x)): desde el lote 10, se quita el 70 % de las legítimas de las categorías
    presenciales (cierre del comercio presencial). Se conservan todos los fraudes. No se fabrican filas.
  - D2, deriva conceptual (P(y|x)): desde el lote 14, la mitad de los fraudes se "camufla": monto típico
    legítimo de su categoría y horario diurno.

Se ejecuta en el Codespace (con proyecto_final/.env) o dentro de los contenedores de Kestra (variables
SNOWFLAKE_* y MLFLOW_TRACKING_URI en el entorno).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from datos import _conectar  # noqa: E402

# ------------------------------------------------------------------------------- simulación
INICIO = pd.Timestamp("2020-07-01")
N_LOTES = 26
HORIZONTE = 2                       # pasos hasta que llega el target de un lote
D1_DESDE, D1_CONSERVA = 10, 0.30    # se conserva el 30 % de las legítimas presenciales
D2_DESDE, D2_FRACCION = 14, 0.50    # se camufla la mitad de los fraudes
SEMILLA_LOTE = 1000                 # semilla del lote k = 1000 + k
D2_HORAS = (9, 17)                  # horario diurno del fraude camuflado (inclusive)
PRESENCIAL = ["gas_transport", "grocery_pos", "home", "shopping_pos", "kids_pets", "entertainment",
              "food_dining", "personal_care", "health_fitness", "misc_pos"]

# ------------------------------------------------------------------------------ reentrenamiento
PASOS_CALENDARIO = (12, 24)         # disparo por calendario cada 12 semanas
PESO_RECIENTES, N_RECIENTES = 5.0, 4  # los 4 lotes etiquetados más recientes pesan 5 veces más

DOCS = RAIZ / "docs"
UMBRALES = DOCS / "monitoreo" / "umbrales.json"     # lo escribe monitoreo/calibrar_umbrales.py
CATALOGOS = json.loads((RAIZ / "api" / "catalogos.json").read_text(encoding="utf-8"))
NOMBRE_MODELO = "centinela-modelo"
ESQUEMA = "PRODUCCION"

COLUMNAS_MODELO = ["amt", "distancia_km", "edad_en_transaccion", "city_pop", "n_tx_1h", "gasto_1h", "n_tx_24h",
                   "gasto_24h", "n_tx_previas", "monto_medio_previo", "monto_relativo", "hora", "dia_semana",
                   "es_nocturna", "es_fin_de_semana", "es_menor_de_edad", "es_multicategoria", "categoria", "canal",
                   "state", "segundos_desde_anterior"]
ENTERAS = ["edad_en_transaccion", "city_pop", "n_tx_1h", "n_tx_24h", "n_tx_previas", "hora", "dia_semana"]
BOOLEANAS = ["es_nocturna", "es_fin_de_semana", "es_menor_de_edad", "es_multicategoria"]


def lote_de(ts: pd.Series) -> np.ndarray:
    """Número de lote semanal (0..25) de cada timestamp de la partición de prueba."""
    return np.minimum(((ts.dt.normalize() - INICIO).dt.days // 7).to_numpy(), N_LOTES - 1)


def umbrales() -> dict:
    return json.loads(UMBRALES.read_text(encoding="utf-8"))


def tipar(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve las 21 entradas del modelo con los tipos de la firma de MLflow."""
    X = df[COLUMNAS_MODELO].copy()
    for c in ENTERAS:
        X[c] = X[c].astype("int64")
    for c in BOOLEANAS:
        X[c] = X[c].astype(bool)
    for c in ("categoria", "canal", "state"):
        X[c] = X[c].astype(str)
    for c in set(COLUMNAS_MODELO) - set(ENTERAS) - set(BOOLEANAS) - {"categoria", "canal", "state"}:
        X[c] = X[c].astype(float)
    return X


# ------------------------------------------------------------------------------------ Snowflake
class Snowflake:
    """Conexión con el par de llaves de CENTINELA_SVC (las mismas credenciales del pipeline)."""

    def __init__(self) -> None:
        self.con = _conectar()
        self.db = self.con.database or os.environ.get("SNOWFLAKE_DATABASE", "CENTINELA")

    def sql(self, consulta: str, params=None) -> pd.DataFrame:
        cur = self.con.cursor()
        cur.execute(consulta, params)
        try:
            df = cur.fetch_pandas_all()
        except Exception:  # noqa: BLE001 - sentencias sin resultado tabular
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        return df

    def ejecutar(self, consulta: str, params=None) -> int:
        cur = self.con.cursor()
        cur.execute(consulta, params)
        return cur.rowcount or 0

    def escribir(self, df: pd.DataFrame, tabla: str, sobrescribir: bool = False) -> int:
        from snowflake.connector.pandas_tools import write_pandas
        d = df.copy()
        d.columns = [c.upper() for c in d.columns]
        ok, _, n, _ = write_pandas(self.con, d, tabla.upper(), schema=ESQUEMA, auto_create_table=True,
                                   overwrite=sobrescribir, quote_identifiers=False, use_logical_type=True)
        if not ok:
            raise RuntimeError(f"write_pandas falló en {tabla}")
        return int(n)

    def existe(self, tabla: str) -> bool:
        r = self.sql(f"SELECT COUNT(*) AS n FROM {self.db}.INFORMATION_SCHEMA.TABLES "
                     f"WHERE TABLE_SCHEMA = '{ESQUEMA}' AND TABLE_NAME = '{tabla.upper()}'")
        return int(r["n"].iloc[0]) > 0

    def cerrar(self) -> None:
        self.con.close()


# --------------------------------------------------------------------------------------- MLflow
def configurar_mlflow():
    """MLFLOW_TRACKING_URI del entorno (contenedores: http://mlflow:5000) o de proyecto_final/.env."""
    import mlflow
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    env = RAIZ / ".env"
    if not uri and env.exists():
        uri = next((l.split("=", 1)[1].strip() for l in env.read_text().splitlines()
                    if l.startswith("MLFLOW_TRACKING_URI=")), None)
    uri = uri or "http://127.0.0.1:5055"
    os.environ["MLFLOW_TRACKING_URI"] = uri
    mlflow.set_tracking_uri(uri)
    return uri


def emitir_salidas(**valores) -> None:
    """Salidas para Kestra (outputs.<tarea>.vars.<nombre>) con el formato ::{"outputs": ...}::."""
    print("::" + json.dumps({"outputs": valores}, ensure_ascii=False, default=str) + "::", flush=True)
