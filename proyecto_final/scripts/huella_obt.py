"""Huella de contenido de la OBT de Centinela, para verificar equivalencia entre cuentas y con el snapshot.

Dos huellas independientes:
  1. sha256_contenido: SHA-256 de un CSV canónico generado en Python.
     - filas ordenadas por trans_num; columnas en orden alfabético (nombres en minúscula);
     - numéricos de punto flotante redondeados a 6 decimales (las sumas de ventanas de Spark
       pueden diferir en el último bit según el orden de las particiones);
     - fechas en ISO 8601; booleanos como 0/1; nulos como cadena vacía.
  2. hash_agg_snowflake: HASH_AGG de Snowflake sobre las mismas columnas con los mismos redondeos
     (no depende del orden y se calcula sin descargar la tabla).

Uso:
  python scripts/huella_obt.py snowflake  --env ../pset_2/.env   # OBT de una cuenta de Snowflake
  python scripts/huella_obt.py parquet    --ruta ../pset_3/data/obt_snapshot.parquet
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

DECIMALES = 6
TABLA = "CENTINELA.OBT.TRANSACCIONES_OBT"


def canonico(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df[sorted(df.columns)].sort_values("trans_num", kind="mergesort").reset_index(drop=True)
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_bool_dtype(s):
            df[c] = s.astype("Int8").astype(str).replace("<NA>", "")
        elif pd.api.types.is_float_dtype(s):
            df[c] = s.round(DECIMALES).map(lambda v: "" if pd.isna(v) else f"{v:.{DECIMALES}f}")
        elif pd.api.types.is_integer_dtype(s):
            df[c] = s.astype("Int64").astype(str).replace("<NA>", "")
        elif pd.api.types.is_datetime64_any_dtype(s):
            df[c] = s.dt.strftime("%Y-%m-%dT%H:%M:%S").fillna("")
        else:
            df[c] = s.map(lambda v: "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v))
    return df


def sha256_contenido(df: pd.DataFrame, bloque: int = 200_000) -> str:
    c = canonico(df)
    h = hashlib.sha256((",".join(c.columns) + "\n").encode())
    for i in range(0, len(c), bloque):
        h.update(c.iloc[i:i + bloque].to_csv(index=False, header=False, lineterminator="\n").encode())
    return h.hexdigest()


def resumen(df: pd.DataFrame) -> dict:
    df = df.rename(columns=str.lower)
    return {"filas": int(len(df)), "fraudes": int(df["is_fraud"].sum()),
            "trans_num_distintos": int(df["trans_num"].nunique()), "columnas": int(df.shape[1]),
            "suma_amt": round(float(df["amt"].astype(float).sum()), 2),
            "sha256_contenido": sha256_contenido(df)}


def sql_hash_agg(columnas_tipos: list[tuple[str, str]]) -> str:
    exprs = []
    for col, tipo in sorted(columnas_tipos):
        t = tipo.upper()
        if t in ("FLOAT", "DOUBLE", "REAL") or t.startswith("NUMBER") and "," in t and not t.endswith(",0)"):
            exprs.append(f"ROUND({col}::FLOAT, {DECIMALES})")
        else:
            exprs.append(col)
    return f"SELECT HASH_AGG({', '.join(exprs)}) FROM {TABLA}"


def desde_snowflake(env: Path) -> dict:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pset_3" / "src"))
    import os
    os.environ["SNOWFLAKE_ENV_FILE"] = str(env.resolve())
    from datos import _conectar
    con = _conectar(); cur = con.cursor()
    cuenta = cur.execute("SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME()").fetchone()[0]
    cur.execute(f"DESC TABLE {TABLA}")
    cols = [(r[0], r[1]) for r in cur.fetchall()]
    hagg = cur.execute(sql_hash_agg(cols)).fetchone()[0]
    df = cur.execute(f"SELECT * FROM {TABLA}").fetch_pandas_all()
    con.close()
    return {"origen": f"snowflake:{TABLA}", "cuenta_hash16": hashlib.sha256(cuenta.encode()).hexdigest()[:16],
            "hash_agg_snowflake": int(hagg), **resumen(df)}


def desde_parquet(ruta: Path) -> dict:
    df = pd.read_parquet(ruta)
    return {"origen": f"parquet:{ruta.name}",
            "sha256_archivo": hashlib.sha256(ruta.read_bytes()).hexdigest(), **resumen(df)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("fuente", choices=["snowflake", "parquet"])
    p.add_argument("--env", type=Path, default=Path("../pset_2/.env"))
    p.add_argument("--ruta", type=Path, default=Path("../pset_3/data/obt_snapshot.parquet"))
    a = p.parse_args()
    t0 = time.time()
    r = desde_snowflake(a.env) if a.fuente == "snowflake" else desde_parquet(a.ruta)
    r.update({"metodo": f"CSV canónico ordenado por trans_num, columnas alfabéticas, floats redondeados a {DECIMALES} decimales",
              "calculado_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "segundos": round(time.time() - t0, 1),
              "pandas": pd.__version__})
    print(json.dumps(r, indent=2, ensure_ascii=False))
