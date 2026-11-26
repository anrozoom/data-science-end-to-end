"""Validación independiente de la OBT: recalcula en SQL (Snowflake) las variables de
ventana para una muestra de transacciones y las compara con las que calculó Spark.

Si Spark hubiera usado la fila actual o filas futuras, los valores no coincidirían
con este cálculo, que solo cuenta transacciones del mismo cliente en [t-86400, t-1] s.

Desde pset_2/:
    docker compose run --rm -v ./scripts:/scripts:ro --entrypoint python dbt /scripts/validar_obt_sql.py
"""
import os

import snowflake.connector

SQL = """
WITH muestra AS (
    SELECT * FROM CENTINELA.OBT.TRANSACCIONES_OBT SAMPLE (5000 ROWS)
),
recalculo AS (
    SELECT m.trans_num,
           m.n_tx_24h, m.n_tx_1h, m.segundos_desde_anterior,
           (SELECT COUNT(*) FROM CENTINELA.GOLD.FCT_TRANSACCIONES f
             WHERE f.cliente_sk = m.cliente_sk
               AND f.trans_epoch BETWEEN DATE_PART(epoch_second, m.trans_ts) - 86400
                                     AND DATE_PART(epoch_second, m.trans_ts) - 1) AS n_tx_24h_sql,
           (SELECT COUNT(*) FROM CENTINELA.GOLD.FCT_TRANSACCIONES f
             WHERE f.cliente_sk = m.cliente_sk
               AND f.trans_epoch BETWEEN DATE_PART(epoch_second, m.trans_ts) - 3600
                                     AND DATE_PART(epoch_second, m.trans_ts) - 1) AS n_tx_1h_sql
    FROM muestra m
)
SELECT COUNT(*)                                        AS filas_muestra,
       SUM(IFF(n_tx_24h = n_tx_24h_sql, 1, 0))         AS n_tx_24h_coinciden,
       SUM(IFF(n_tx_1h = n_tx_1h_sql, 1, 0))           AS n_tx_1h_coinciden,
       SUM(IFF(segundos_desde_anterior < 0, 1, 0))     AS segundos_negativos
FROM recalculo
"""


def main():
    con = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
        role=os.environ["SNOWFLAKE_ROLE"], warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"], authenticator="SNOWFLAKE_JWT",
        private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        private_key_file_pwd=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None)
    cur = con.cursor()
    fila = cur.execute(SQL).fetchone()
    cols = [c[0].lower() for c in cur.description]
    for c, v in zip(cols, fila):
        print(f"{c}: {v}")
    tot = cur.execute("""
        SELECT (SELECT COUNT(*) FROM CENTINELA.OBT.TRANSACCIONES_OBT) AS filas_obt,
               (SELECT COUNT(DISTINCT trans_num) FROM CENTINELA.OBT.TRANSACCIONES_OBT) AS trans_num_distintos,
               (SELECT COUNT(*) FROM CENTINELA.GOLD.FCT_TRANSACCIONES) AS filas_fct,
               (SELECT AVG(is_fraud) FROM CENTINELA.OBT.TRANSACCIONES_OBT) AS tasa_fraude_obt
    """).fetchone()
    for c, v in zip([d[0].lower() for d in cur.description], tot):
        print(f"{c}: {v}")
    con.close()


if __name__ == "__main__":
    main()
