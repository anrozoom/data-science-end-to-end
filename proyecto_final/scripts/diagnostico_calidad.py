"""Diagnóstico de calidad de CENTINELA.RAW.TRANSACCIONES (antes de transformar).

Corre cada consulta de calidad (completitud, precisión, consistencia y validez)
y escribe los resultados reales en docs/calidad_resultados.md, junto con el SQL
exacto que produjo cada cifra.

Desde pset_2/:
    docker compose run --rm -v ./scripts:/scripts:ro -v ./docs:/docs \
        --entrypoint python dbt /scripts/diagnostico_calidad.py
"""
import os
import time

import snowflake.connector

T = "RAW.TRANSACCIONES"
TS = "TRY_TO_TIMESTAMP_NTZ(TRANS_DATE_TRANS_TIME, 'YYYY-MM-DD HH24:MI:SS')"
DOB = "TRY_TO_DATE(DOB, 'YYYY-MM-DD')"

COLUMNAS = ["INDICE_ORIGEN", "TRANS_DATE_TRANS_TIME", "CC_NUM", "MERCHANT", "CATEGORY",
            "AMT", "FIRST", "LAST", "GENDER", "STREET", "CITY", "STATE", "ZIP", "LAT",
            "LONG", "CITY_POP", "JOB", "DOB", "TRANS_NUM", "UNIX_TIME", "MERCH_LAT",
            "MERCH_LONG", "IS_FRAUD"]

CONSULTAS = [
    # ------------------------------------------------------------------ volumen
    ("Volumen", "Filas totales, por archivo de origen y tasa de fraude",
     f"""SELECT _SOURCE_FILE, COUNT(*) AS filas,
                SUM(IFF(IS_FRAUD = '1', 1, 0)) AS fraudes,
                ROUND(100 * AVG(IFF(IS_FRAUD = '1', 1, 0)), 3) AS pct_fraude
         FROM {T} GROUP BY ROLLUP(_SOURCE_FILE) ORDER BY _SOURCE_FILE NULLS LAST"""),
    ("Volumen", "Cobertura de fechas cargadas (_LOAD_DATE)",
     f"""SELECT MIN(_LOAD_DATE) AS primera, MAX(_LOAD_DATE) AS ultima,
                COUNT(DISTINCT _LOAD_DATE) AS dias_con_datos,
                DATEDIFF('day', MIN(_LOAD_DATE), MAX(_LOAD_DATE)) + 1 AS dias_calendario,
                ROUND(COUNT(*) / COUNT(DISTINCT _LOAD_DATE), 0) AS filas_por_dia_prom
         FROM {T}"""),
    ("Volumen", "Días del calendario 2019-2020 sin ninguna transacción",
     f"""WITH cal AS (SELECT DATEADD('day', SEQ4(), '2019-01-01'::DATE) AS d
                      FROM TABLE(GENERATOR(ROWCOUNT => 731)))
         SELECT d AS dia_sin_datos FROM cal
         WHERE d NOT IN (SELECT DISTINCT _LOAD_DATE FROM {T}) ORDER BY d"""),
    # -------------------------------------------------------------- completitud
    ("Completitud", "Nulos o vacíos por columna",
     "SELECT " + ",\n                ".join(
         f"SUM(IFF({c} IS NULL OR TRIM({c}) = '', 1, 0)) AS {c}" for c in COLUMNAS)
     + f"\n         FROM {T}"),
    # ---------------------------------------------------------------- precisión
    ("Precisión", "Duplicados por trans_num (clave de la transacción)",
     f"""SELECT COUNT(*) AS filas, COUNT(DISTINCT TRANS_NUM) AS trans_num_distintos,
                COUNT(*) - COUNT(DISTINCT TRANS_NUM) AS filas_duplicadas
         FROM {T}"""),
    ("Precisión", "Filas idénticas en todas las columnas de negocio",
     f"""SELECT COUNT(*) - COUNT(DISTINCT HASH({', '.join(COLUMNAS[1:])})) AS filas_identicas_repetidas
         FROM {T}"""),
    ("Precisión", "Índice original (columna sin nombre) repetido entre archivos",
     f"""SELECT COUNT(*) AS filas, COUNT(DISTINCT INDICE_ORIGEN) AS indices_distintos,
                COUNT(DISTINCT _SOURCE_FILE || '|' || INDICE_ORIGEN) AS indices_por_archivo
         FROM {T}"""),
    ("Precisión", "Transacciones del día frontera presentes en ambos archivos",
     f"""SELECT _LOAD_DATE, _SOURCE_FILE, COUNT(*) AS filas
         FROM {T}
         WHERE _LOAD_DATE IN (SELECT _LOAD_DATE FROM {T} GROUP BY 1 HAVING COUNT(DISTINCT _SOURCE_FILE) > 1)
         GROUP BY 1, 2 ORDER BY 1, 2"""),
    # ------------------------------------------------------------- consistencia
    ("Consistencia", "Formato de fechas (texto en RAW)",
     f"""SELECT SUM(IFF({TS} IS NULL, 1, 0)) AS trans_date_no_parseable,
                SUM(IFF({DOB} IS NULL, 1, 0)) AS dob_no_parseable,
                SUM(IFF(TRY_TO_NUMBER(UNIX_TIME) IS NULL, 1, 0)) AS unix_time_no_numerico
         FROM {T}"""),
    ("Consistencia", "unix_time frente a trans_date_trans_time (diferencia en días)",
     f"""SELECT MIN(d) AS dif_min_dias, MAX(d) AS dif_max_dias, COUNT(DISTINCT d) AS valores_distintos
         FROM (SELECT DATEDIFF('day', {TS}, TO_TIMESTAMP_NTZ(TRY_TO_NUMBER(UNIX_TIME))) AS d FROM {T})"""),
    ("Consistencia", "Prefijo artificial 'fraud_' en merchant",
     f"""SELECT SUM(IFF(STARTSWITH(MERCHANT, 'fraud_'), 1, 0)) AS con_prefijo,
                ROUND(100 * AVG(IFF(STARTSWITH(MERCHANT, 'fraud_'), 1, 0)), 2) AS pct_con_prefijo,
                COUNT(DISTINCT MERCHANT) AS comercios_distintos
         FROM {T}"""),
    ("Consistencia", "Atributos del cliente estables por cc_num",
     f"""SELECT COUNT(*) AS clientes,
                SUM(IFF(n_nombre > 1, 1, 0)) AS con_varios_nombres,
                SUM(IFF(n_dob > 1, 1, 0)) AS con_varias_dob,
                SUM(IFF(n_dir > 1, 1, 0)) AS con_varias_direcciones,
                SUM(IFF(n_geo > 1, 1, 0)) AS con_varias_lat_long,
                SUM(IFF(n_job > 1, 1, 0)) AS con_varios_job
         FROM (SELECT CC_NUM,
                      COUNT(DISTINCT FIRST || ' ' || LAST || GENDER) AS n_nombre,
                      COUNT(DISTINCT DOB) AS n_dob,
                      COUNT(DISTINCT STREET || CITY || STATE || ZIP) AS n_dir,
                      COUNT(DISTINCT LAT || ',' || LONG) AS n_geo,
                      COUNT(DISTINCT JOB) AS n_job
               FROM {T} GROUP BY CC_NUM)"""),
    ("Consistencia", "Atributos del comercio: categoría y ubicación por merchant",
     f"""SELECT COUNT(*) AS comercios,
                SUM(IFF(n_cat > 1, 1, 0)) AS con_varias_categorias,
                SUM(IFF(n_geo > 1, 1, 0)) AS con_varias_ubicaciones,
                ROUND(AVG(n_geo), 1) AS ubicaciones_prom_por_comercio
         FROM (SELECT MERCHANT, COUNT(DISTINCT CATEGORY) AS n_cat,
                      COUNT(DISTINCT MERCH_LAT || ',' || MERCH_LONG) AS n_geo
               FROM {T} GROUP BY MERCHANT)"""),
    ("Consistencia", "Valores distintos de columnas categóricas",
     f"""SELECT COUNT(DISTINCT CATEGORY) AS categorias, COUNT(DISTINCT GENDER) AS generos,
                LISTAGG(DISTINCT GENDER, ',') AS valores_gender,
                COUNT(DISTINCT STATE) AS estados, COUNT(DISTINCT JOB) AS ocupaciones,
                COUNT(DISTINCT CC_NUM) AS tarjetas
         FROM {T}"""),
    # ------------------------------------------------------------------ validez
    ("Validez", "Monto (amt)",
     f"""SELECT SUM(IFF(TRY_TO_DECIMAL(AMT, 12, 2) IS NULL, 1, 0)) AS no_numerico,
                SUM(IFF(TRY_TO_DECIMAL(AMT, 12, 2) <= 0, 1, 0)) AS menor_o_igual_cero,
                MIN(TRY_TO_DECIMAL(AMT, 12, 2)) AS minimo, MAX(TRY_TO_DECIMAL(AMT, 12, 2)) AS maximo,
                MEDIAN(TRY_TO_DECIMAL(AMT, 12, 2)) AS mediana,
                SUM(IFF(TRY_TO_DECIMAL(AMT, 12, 2) > 10000, 1, 0)) AS mayor_a_10000
         FROM {T}"""),
    ("Validez", "Coordenadas fuera de rango",
     f"""SELECT SUM(IFF(TRY_TO_DOUBLE(LAT) NOT BETWEEN -90 AND 90 OR TRY_TO_DOUBLE(LAT) IS NULL, 1, 0)) AS lat_invalida,
                SUM(IFF(TRY_TO_DOUBLE(LONG) NOT BETWEEN -180 AND 180 OR TRY_TO_DOUBLE(LONG) IS NULL, 1, 0)) AS long_invalida,
                SUM(IFF(TRY_TO_DOUBLE(MERCH_LAT) NOT BETWEEN -90 AND 90 OR TRY_TO_DOUBLE(MERCH_LAT) IS NULL, 1, 0)) AS merch_lat_invalida,
                SUM(IFF(TRY_TO_DOUBLE(MERCH_LONG) NOT BETWEEN -180 AND 180 OR TRY_TO_DOUBLE(MERCH_LONG) IS NULL, 1, 0)) AS merch_long_invalida,
                MIN(TRY_TO_DOUBLE(LAT)) AS lat_min, MAX(TRY_TO_DOUBLE(LAT)) AS lat_max,
                MIN(TRY_TO_DOUBLE(LONG)) AS long_min, MAX(TRY_TO_DOUBLE(LONG)) AS long_max
         FROM {T}"""),
    ("Validez", "Edad del titular en la fecha de la transacción",
     f"""SELECT MIN(e) AS edad_min, MAX(e) AS edad_max,
                SUM(IFF(e < 18, 1, 0)) AS menores_de_18, SUM(IFF(e > 100, 1, 0)) AS mayores_de_100
         FROM (SELECT DATEDIFF('year', {DOB}, {TS})
                      - IFF(DATEADD('year', DATEDIFF('year', {DOB}, {TS}), {DOB}) > {TS}::DATE, 1, 0) AS e
               FROM {T})"""),
    ("Validez", "Rango de fechas de transacción y valores del target",
     f"""SELECT MIN({TS}) AS primera_transaccion, MAX({TS}) AS ultima_transaccion,
                SUM(IFF({TS} NOT BETWEEN '2019-01-01' AND '2020-12-31 23:59:59', 1, 0)) AS fuera_de_2019_2020,
                SUM(IFF(IS_FRAUD NOT IN ('0', '1') OR IS_FRAUD IS NULL, 1, 0)) AS is_fraud_invalido
         FROM {T}"""),
    ("Validez", "Otros campos: city_pop, zip y cc_num",
     f"""SELECT SUM(IFF(TRY_TO_NUMBER(CITY_POP) IS NULL OR TRY_TO_NUMBER(CITY_POP) <= 0, 1, 0)) AS city_pop_invalida,
                SUM(IFF(NOT REGEXP_LIKE(ZIP, '[0-9]{{3,5}}'), 1, 0)) AS zip_no_numerico,
                SUM(IFF(LENGTH(ZIP) < 5, 1, 0)) AS zip_menos_de_5_digitos,
                MIN(LENGTH(CC_NUM)) AS cc_num_largo_min, MAX(LENGTH(CC_NUM)) AS cc_num_largo_max,
                SUM(IFF(TRY_TO_NUMBER(CC_NUM) IS NULL, 1, 0)) AS cc_num_no_numerico
         FROM {T}"""),
]


def conectar():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
        role=os.environ["SNOWFLAKE_ROLE"], warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"], schema="RAW",
        authenticator="SNOWFLAKE_JWT",
        private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        private_key_file_pwd=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
    )


def tabla_md(cols, filas):
    def fmt(v):
        if isinstance(v, float):
            return f"{v:,.4f}".rstrip("0").rstrip(".")
        if isinstance(v, int):
            return f"{v:,}"
        return "" if v is None else str(v)
    if not filas:
        return "_(sin filas)_\n"
    out = ["| " + " | ".join(c.lower() for c in cols) + " |",
           "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(fmt(v) for v in f) + " |" for f in filas]
    return "\n".join(out) + "\n"


def main():
    con = conectar()
    cur = con.cursor()
    total = cur.execute(f"SELECT COUNT(*) FROM {T}").fetchone()[0]
    partes = [
        "# Resultados del diagnóstico de calidad (RAW)\n",
        f"> Generado automáticamente por `scripts/diagnostico_calidad.py` el "
        f"{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} sobre **{total:,} filas** de "
        f"`CENTINELA.{T}`. No editar a mano: volver a correr el script.\n",
    ]
    dimension = None
    for dim, titulo, sql in CONSULTAS:
        if dim != dimension:
            partes.append(f"\n## {dim}\n")
            dimension = dim
        filas = cur.execute(sql).fetchall()
        cols = [c[0] for c in cur.description]
        partes.append(f"\n### {titulo}\n\n{tabla_md(cols, filas)}\n"
                      f"<details><summary>SQL</summary>\n\n```sql\n{sql.strip()}\n```\n</details>\n")
        print(f"OK  {dim}: {titulo}")
    con.close()
    salida = "/docs/calidad_resultados.md"
    with open(salida, "w", encoding="utf-8") as f:
        f.write("\n".join(partes))
    print(f"Escrito {salida} ({total:,} filas analizadas)")


if __name__ == "__main__":
    main()
