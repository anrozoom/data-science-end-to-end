"""Construye la One Big Table (OBT) de Centinela a partir de GOLD y la escribe en Snowflake.

GRANO: una fila por transacción (trans_num), igual que fct_transacciones.

1. Lee de CENTINELA.GOLD el hecho y las 5 dimensiones (conector Spark-Snowflake).
2. Une el hecho con las dimensiones (left join por clave sustituta).
3. Calcula variables de comportamiento por cliente con funciones de ventana,
   ordenadas por tiempo y EXCLUYENDO la fila actual y todo lo futuro (sin fuga):
     - n_tx_1h, gasto_1h, n_tx_24h, gasto_24h: ventanas de rango [t-3600, t-1] y [t-86400, t-1] s
     - segundos_desde_anterior: tiempo desde la transacción anterior del cliente
     - n_tx_previas, monto_medio_previo, monto_relativo: historial previo del cliente
4. Valida que los joins no dupliquen ni pierdan filas y escribe CENTINELA.OBT.TRANSACCIONES_OBT.

Se ejecuta con spark/ejecutar_obt.sh (spark-submit dentro del contenedor spark-master).
"""
import json
import os
import subprocess
import sys
import time

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

SALIDA = "/opt/spark-jobs/salida/validaciones_obt.json"
TABLA_OBT = "TRANSACCIONES_OBT"
_LLAVE = None  # llave descifrada, solo en memoria del driver


def llave_sin_cifrar() -> str:
    """Descifra la llave privada en memoria (nunca a disco) y devuelve el cuerpo PEM.

    El conector Spark-Snowflake solo acepta la llave PKCS#8 sin cifrar en la opción
    pem_private_key. La passphrase va a openssl por variable de entorno, no por argumento.
    """
    global _LLAVE
    if _LLAVE:
        return _LLAVE
    ruta = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    cmd = ["openssl", "pkcs8", "-in", ruta]
    if os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"):
        cmd += ["-passin", "env:SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"]
    cmd += ["-topk8", "-nocrypt", "-outform", "PEM"]
    pem = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    _LLAVE = "".join(l for l in pem.splitlines() if "-----" not in l)
    return _LLAVE


def opciones_snowflake(esquema: str) -> dict:
    return {
        "sfURL": f"{os.environ['SNOWFLAKE_ACCOUNT']}.snowflakecomputing.com",
        "sfUser": os.environ["SNOWFLAKE_USER"],
        "sfRole": os.environ["SNOWFLAKE_ROLE"],
        "sfWarehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "sfDatabase": os.environ["SNOWFLAKE_DATABASE"],
        "sfSchema": esquema,
        "pem_private_key": llave_sin_cifrar(),
        "sfTimezone": "UTC",
    }


def leer(spark, esquema, tabla):
    df = (spark.read.format("snowflake").options(**opciones_snowflake(esquema))
          .option("dbtable", tabla).load())
    return df.toDF(*[c.lower() for c in df.columns])


def main() -> int:
    inicio = time.time()
    spark = (SparkSession.builder.appName("centinela-obt")
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.shuffle.partitions", "16")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")

    # ------------------------------------------------------------------ lectura
    fct = leer(spark, "GOLD", "FCT_TRANSACCIONES").cache()
    dim_cliente = leer(spark, "GOLD", "DIM_CLIENTE")
    dim_comercio = leer(spark, "GOLD", "DIM_COMERCIO")
    dim_categoria = leer(spark, "GOLD", "DIM_CATEGORIA")
    dim_fecha = leer(spark, "GOLD", "DIM_FECHA")
    dim_hora = leer(spark, "GOLD", "DIM_HORA")

    n_fct = fct.count()
    fraude_fct = fct.agg(F.avg(F.col("is_fraud").cast("double"))).first()[0]
    print(f"fct_transacciones: {n_fct} filas, tasa de fraude {fraude_fct:.6f}")

    # -------------------------------------------------------------------- joins
    # Solo atributos útiles para el modelo: sin nombres, calle ni cc_num (sintéticos/PII).
    cli = dim_cliente.select(
        "cliente_sk", "gender", "state", "city_pop", "job",
        F.col("lat").alias("cliente_lat"), F.col("long").alias("cliente_long"))
    com = dim_comercio.select("comercio_sk", "comercio", "es_multicategoria")
    cat = dim_categoria.select("categoria_sk", "categoria", "canal")
    fec = dim_fecha.select("fecha_sk", "fecha", "anio", "mes", "dia_semana",
                           "es_fin_de_semana", "particion_temporal")
    hor = dim_hora.select("hora_sk", F.col("hora"), "es_nocturna", "franja")

    base = (fct
            .join(F.broadcast(cli), "cliente_sk", "left")
            .join(F.broadcast(com), "comercio_sk", "left")
            .join(F.broadcast(cat), "categoria_sk", "left")
            .join(F.broadcast(fec), "fecha_sk", "left")
            .join(F.broadcast(hor), "hora_sk", "left")
            .withColumn("t", F.col("trans_epoch").cast("long"))
            .withColumn("amt_d", F.col("amt").cast("double")))

    # --------------------------------------------- variables de comportamiento
    # Rango en segundos sobre la época; el límite superior -1 excluye la fila actual
    # (y cualquier transacción del mismo segundo) y todo lo posterior.
    por_tiempo = Window.partitionBy("cliente_sk").orderBy("t")
    w_1h = por_tiempo.rangeBetween(-3600, -1)
    w_24h = por_tiempo.rangeBetween(-86400, -1)
    # Para el historial previo, orden total (t, trans_num) y filas estrictamente anteriores.
    por_orden = Window.partitionBy("cliente_sk").orderBy("t", "trans_num")
    w_previas = por_orden.rowsBetween(Window.unboundedPreceding, -1)

    obt = (base
           .withColumn("n_tx_1h", F.count("*").over(w_1h))
           .withColumn("gasto_1h", F.coalesce(F.sum("amt_d").over(w_1h), F.lit(0.0)))
           .withColumn("n_tx_24h", F.count("*").over(w_24h))
           .withColumn("gasto_24h", F.coalesce(F.sum("amt_d").over(w_24h), F.lit(0.0)))
           .withColumn("segundos_desde_anterior", F.col("t") - F.lag("t").over(por_orden))
           .withColumn("n_tx_previas", F.count("*").over(w_previas))
           .withColumn("monto_medio_previo", F.avg("amt_d").over(w_previas))
           .withColumn("monto_relativo", F.col("amt_d") / F.col("monto_medio_previo"))
           .select(
               "trans_num", "trans_ts", "fecha", "anio", "mes", "dia_semana",
               "es_fin_de_semana", "hora", "es_nocturna", "franja", "particion_temporal",
               "cliente_sk", "gender", "state", "city_pop", "job", "cliente_lat", "cliente_long",
               "edad_en_transaccion", "es_menor_de_edad",
               "comercio_sk", "comercio", "es_multicategoria", "categoria_sk", "categoria", "canal",
               F.col("amt_d").alias("amt"), "merch_lat", "merch_long", "distancia_km",
               "n_tx_1h", "gasto_1h", "n_tx_24h", "gasto_24h", "segundos_desde_anterior",
               "n_tx_previas", "monto_medio_previo", "monto_relativo",
               F.col("is_fraud").cast("int").alias("is_fraud"), "source_file")
           .cache())

    # ------------------------------------------------------------- validaciones
    n_obt = obt.count()
    n_distintos = obt.select("trans_num").distinct().count()
    fraude_obt = obt.agg(F.avg("is_fraud")).first()[0]
    claves = ["trans_num", "cliente_sk", "comercio_sk", "categoria_sk", "fecha", "hora",
              "categoria", "comercio", "gender", "particion_temporal"]
    nulos = obt.select([F.sum(F.col(c).isNull().cast("int")).alias(c) for c in claves]).first().asDict()
    n_clientes = obt.select("cliente_sk").distinct().count()
    sin_anterior = obt.filter(F.col("segundos_desde_anterior").isNull()).count()
    negativos = obt.filter((F.col("segundos_desde_anterior") < 0) | (F.col("n_tx_1h") > F.col("n_tx_24h"))).count()

    chequeos = {
        "count(OBT) == count(fct_transacciones)": n_obt == n_fct,
        "count(distinct trans_num) == count(OBT)": n_distintos == n_obt,
        "tasa de is_fraud igual antes y después de los joins": abs(fraude_obt - fraude_fct) < 1e-12,
        "0 nulos en claves y atributos de dimensiones": all(v == 0 for v in nulos.values()),
        "sin anterior == 1 por cliente (primera transacción)": sin_anterior == n_clientes,
        "ventanas coherentes (diferencias >= 0, n_tx_1h <= n_tx_24h)": negativos == 0,
    }
    resultado = {
        "generado_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "grano": "una fila por transacción (trans_num)",
        "filas_fct_transacciones": n_fct,
        "filas_obt": n_obt,
        "trans_num_distintos_obt": n_distintos,
        "tasa_fraude_fct": fraude_fct,
        "tasa_fraude_obt": fraude_obt,
        "nulos_en_claves": nulos,
        "clientes": n_clientes,
        "filas_sin_transaccion_anterior": sin_anterior,
        "filas_con_ventanas_incoherentes": negativos,
        "columnas_obt": obt.columns,
        "chequeos": chequeos,
    }
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))
    if not all(chequeos.values()):
        print("VALIDACIÓN FALLIDA: no se escribe la OBT", file=sys.stderr)
        return 1

    # ---------------------------------------------------------------- escritura
    (obt.write.format("snowflake").options(**opciones_snowflake("OBT"))
     .option("dbtable", TABLA_OBT).mode("overwrite").save())

    # Relee el conteo desde Snowflake para confirmar que la escritura quedó completa.
    escrita = (spark.read.format("snowflake").options(**opciones_snowflake("OBT"))
               .option("query", f"SELECT COUNT(*) AS N FROM {TABLA_OBT}").load().first()[0])
    resultado["filas_escritas_en_snowflake"] = int(escrita)
    resultado["chequeos"]["filas en Snowflake == count(OBT)"] = int(escrita) == n_obt
    resultado["duracion_s"] = round(time.time() - inicio, 1)
    print(f"Escrita CENTINELA.OBT.{TABLA_OBT}: {escrita} filas en {resultado['duracion_s']} s")

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    spark.stop()
    return 0 if all(resultado["chequeos"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
