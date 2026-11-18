"""Lectura de la OBT de Centinela y snapshot local en Parquet.

La OBT vive en Snowflake (CENTINELA.OBT.TRANSACCIONES_OBT, construida en el PSet 2).
Los notebooks NO leen Snowflake directamente: leen un snapshot local en Parquet,
con su fecha de corte y su hash SHA-256, para que cada corrida de MLflow registre
exactamente qué datos usó (y para no depender de la cuenta de prueba de Snowflake).

Crear o recrear el snapshot (desde pset_3/):
    python src/datos.py

Credenciales: las mismas del PSet 2, leídas de pset_2/.env (par de llaves de
CENTINELA_SVC). Para otra cuenta, basta con apuntar SNOWFLAKE_ENV_FILE a otro .env
con las variables SNOWFLAKE_* (ver pset_3/.env.example).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]           # pset_3/
DIR_DATOS = RAIZ / "data"
RUTA_PARQUET = DIR_DATOS / "obt_snapshot.parquet"
RUTA_META = DIR_DATOS / "obt_snapshot.json"
TABLA_ORIGEN = "CENTINELA.OBT.TRANSACCIONES_OBT"
OBJETIVO = "is_fraud"


def _leer_env(ruta: Path) -> dict:
    """Lee un .env KEY=VALUE sin ejecutarlo."""
    valores = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            valores[k.strip()] = v.strip()
    return valores


def _conectar():
    import snowflake.connector

    env_file = Path(os.environ.get("SNOWFLAKE_ENV_FILE", RAIZ.parent / "pset_2" / ".env"))
    cfg = {**_leer_env(env_file), **{k: v for k, v in os.environ.items() if k.startswith("SNOWFLAKE_")}}
    # En el .env del PSet 2 la ruta de la llave es la de los contenedores (/secrets/...).
    llave = Path(cfg["SNOWFLAKE_PRIVATE_KEY_PATH"])
    if not llave.exists():
        llave = env_file.parent / "secrets" / llave.name
    return snowflake.connector.connect(
        account=cfg["SNOWFLAKE_ACCOUNT"], user=cfg["SNOWFLAKE_USER"], role=cfg["SNOWFLAKE_ROLE"],
        warehouse=cfg["SNOWFLAKE_WAREHOUSE"], database=cfg["SNOWFLAKE_DATABASE"],
        authenticator="SNOWFLAKE_JWT", private_key_file=str(llave),
        private_key_file_pwd=cfg.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
    )


def hash_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def crear_snapshot() -> dict:
    """Descarga la OBT completa de Snowflake y la guarda como Parquet + metadatos."""
    inicio = time.time()
    con = _conectar()
    cur = con.cursor()
    corte = cur.execute("SELECT CURRENT_TIMESTAMP()::STRING").fetchone()[0]
    cur.execute(f"SELECT * FROM {TABLA_ORIGEN} ORDER BY TRANS_TS, TRANS_NUM")
    df = cur.fetch_pandas_all()
    con.close()
    df.columns = [c.lower() for c in df.columns]
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RUTA_PARQUET, index=False)
    meta = {
        "tabla_origen": TABLA_ORIGEN,
        "fecha_corte_snapshot": corte,
        "filas": int(len(df)),
        "columnas": int(df.shape[1]),
        "tasa_fraude": float(df[OBJETIVO].mean()),
        "sha256": hash_archivo(RUTA_PARQUET),
        "segundos_descarga": round(time.time() - inicio, 1),
    }
    RUTA_META.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def metadatos_snapshot() -> dict:
    """Metadatos del snapshot (tabla, fecha de corte, hash) para registrar en MLflow."""
    meta = json.loads(RUTA_META.read_text(encoding="utf-8"))
    actual = hash_archivo(RUTA_PARQUET)
    if actual != meta["sha256"]:
        raise RuntimeError("El Parquet no coincide con el hash registrado: recrea el snapshot.")
    return meta


def cargar_obt(columnas: list[str] | None = None) -> pd.DataFrame:
    """Lee el snapshot local (verifica antes su hash)."""
    metadatos_snapshot()
    df = pd.read_parquet(RUTA_PARQUET, columns=columnas)
    for c in df.columns:
        if pd.api.types.is_object_dtype(df[c]) and c in ("es_fin_de_semana", "es_nocturna",
                                                         "es_menor_de_edad", "es_multicategoria"):
            df[c] = df[c].astype(bool)
    return df


if __name__ == "__main__":
    print(json.dumps(crear_snapshot(), indent=2, ensure_ascii=False))
