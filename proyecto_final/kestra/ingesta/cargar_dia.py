"""Ingesta a RAW: una fecha (trigger diario) o un rango (backfill), en paralelo.

La fuente (Kaggle, kartik2112/fraud-detection) es un archivo estático de dos años.
Para simular una ingesta diaria:
  1. La primera ejecución descarga el dataset una sola vez al volumen /data y lo
     divide en un archivo por día (/data/dias/AAAA-MM-DD.csv). Un candado de archivo
     evita que dos ejecuciones concurrentes descarguen a la vez.
  2. Cada ejecución sube el archivo de su fecha a un stage de Snowflake y lo copia
     a RAW.TRANSACCIONES dentro de una transacción: si la fecha ya tenía filas, las
     borra antes (idempotente: un reintento o una re-ejecución no duplica filas).
  3. Verifica que las filas cargadas sean exactamente las del archivo del día.

RAW guarda los datos tal como vienen (todo como texto) más tres columnas de
auditoría: _SOURCE_FILE, _LOAD_DATE y _INGESTED_AT.

Variables de entorno: FECHA (AAAA-MM-DD), SNOWFLAKE_* , SNOWFLAKE_PRIVATE_KEY (PEM),
KAGGLE_API_TOKEN, y para la demostración de reintentos SIMULAR_FALLA y EJECUCION_ID.
"""
import csv
import fcntl
import os
import re
import shutil
import sys
import time
from pathlib import Path

DATOS = Path(os.environ.get("DATOS", "/data"))
CRUDOS = DATOS / "raw"
DIAS = DATOS / "dias"
MARCA = DATOS / ".preparado"
CANDADO = DATOS / ".candado"
DATASET = "kartik2112/fraud-detection"
ARCHIVOS = ["fraudTrain.csv", "fraudTest.csv"]

# Encabezado original (la primera columna no tiene nombre: es el índice de pandas).
ENCABEZADO = ["", "trans_date_trans_time", "cc_num", "merchant", "category", "amt",
              "first", "last", "gender", "street", "city", "state", "zip", "lat",
              "long", "city_pop", "job", "dob", "trans_num", "unix_time",
              "merch_lat", "merch_long", "is_fraud"]
# Nombres en RAW: los mismos, en mayúsculas; el índice sin nombre pasa a INDICE_ORIGEN.
COLUMNAS_RAW = ["INDICE_ORIGEN"] + [c.upper() for c in ENCABEZADO[1:]]
FECHA_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) ")

TABLA = "RAW.TRANSACCIONES"
STAGE = "RAW.STG_TRANSACCIONES"
FORMATO = ("TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '\"' "
           "EMPTY_FIELD_AS_NULL = FALSE ENCODING = 'UTF8'")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ----------------------------------------------------------------------------
# 1. Preparación de la fuente (una sola vez)
# ----------------------------------------------------------------------------
def preparar_fuente() -> None:
    if MARCA.exists():
        return
    DATOS.mkdir(parents=True, exist_ok=True)
    with open(CANDADO, "w") as candado:
        log("Esperando el candado de preparación de la fuente...")
        fcntl.flock(candado, fcntl.LOCK_EX)
        if MARCA.exists():  # otra ejecución la preparó mientras esperábamos
            return
        descargar()
        dividir_por_dia()
        MARCA.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))


def descargar() -> None:
    if all((CRUDOS / a).exists() for a in ARCHIVOS):
        log(f"Fuente ya descargada en {CRUDOS}; no se vuelve a bajar.")
        return
    CRUDOS.mkdir(parents=True, exist_ok=True)
    log(f"Descargando {DATASET} desde Kaggle (una sola vez)...")
    from kaggle.api.kaggle_api_extended import KaggleApi  # lee KAGGLE_API_TOKEN

    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(DATASET, path=str(CRUDOS), unzip=True, quiet=True)
    for a in ARCHIVOS:
        if not (CRUDOS / a).exists():
            raise RuntimeError(f"La descarga no trajo {a}")
    log("Descarga completa.")


def dividir_por_dia() -> None:
    """Divide los dos CSV en un archivo por fecha de transacción, sin limpiar nada."""
    tmp = DATOS / "dias_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    conteo_archivo = {}
    invalidas = 0
    for nombre in ARCHIVOS:
        n = 0
        actual, salida, escritor = None, None, None
        with open(CRUDOS / nombre, newline="", encoding="utf-8") as f:
            lector = csv.reader(f)
            encabezado = next(lector)
            if encabezado != ENCABEZADO:
                raise RuntimeError(f"Encabezado inesperado en {nombre}: {encabezado}")
            for fila in lector:
                n += 1
                m = FECHA_RE.match(fila[1]) if len(fila) > 1 else None
                fecha = m.group(1) if m else "_invalidas"
                invalidas += fecha == "_invalidas"
                if fecha != actual:
                    if salida:
                        salida.close()
                    destino = tmp / f"{fecha}.csv"
                    nuevo = not destino.exists()
                    salida = open(destino, "a", newline="", encoding="utf-8")
                    escritor = csv.writer(salida, quoting=csv.QUOTE_ALL)
                    if nuevo:
                        escritor.writerow(COLUMNAS_RAW + ["_SOURCE_FILE", "_LOAD_DATE"])
                    actual = fecha
                escritor.writerow(fila + [nombre, fecha])
        if salida:
            salida.close()
        conteo_archivo[nombre] = n
        log(f"{nombre}: {n} filas de datos")
    shutil.rmtree(DIAS, ignore_errors=True)
    tmp.rename(DIAS)
    dias = len([p for p in DIAS.glob("*.csv") if not p.name.startswith("_")])
    log(f"División lista: {dias} archivos diarios; filas sin fecha reconocible: {invalidas}; "
        f"total filas: {sum(conteo_archivo.values())}")


# ----------------------------------------------------------------------------
# 2. Carga idempotente de una fecha
# ----------------------------------------------------------------------------
def conectar():
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    frase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    llave = serialization.load_pem_private_key(
        os.environ["SNOWFLAKE_PRIVATE_KEY"].encode(),
        password=frase.encode() if frase else None,
    )
    der = llave.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema="RAW",
        private_key=der,
        login_timeout=60,
        network_timeout=300,
    )


def crear_objetos(cur) -> None:
    columnas = ",\n  ".join(f"{c} VARCHAR" for c in COLUMNAS_RAW)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLA} (
          {columnas},
          _SOURCE_FILE VARCHAR,
          _LOAD_DATE DATE,
          _INGESTED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
        ) COMMENT = 'Transacciones Sparkov tal como vienen de Kaggle (todo texto)'""")
    cur.execute(f"CREATE STAGE IF NOT EXISTS {STAGE} FILE_FORMAT = ({FORMATO})")


def filas_en_archivo(archivo: Path) -> int:
    with open(archivo, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def cargar_fecha(fecha: str, forzar: bool = True) -> int:
    archivo = DIAS / f"{fecha}.csv"
    if not archivo.exists():
        log(f"No hay transacciones para {fecha} (la fuente cubre 2019-01-01 a 2020-12-31). "
            "Nada que cargar.")
        return 0
    esperadas = filas_en_archivo(archivo)
    con = conectar()
    try:
        cur = con.cursor()
        if not forzar:
            ya = cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE _LOAD_DATE = %s", (fecha,)).fetchone()[0]
            if ya == esperadas:
                log(f"{fecha}: ya completo ({ya} filas); se omite (forzar=false).")
                return ya
        cur.execute(f"PUT 'file://{archivo}' @{STAGE}/{fecha}/ OVERWRITE = TRUE AUTO_COMPRESS = TRUE")
        lista = ", ".join(COLUMNAS_RAW + ["_SOURCE_FILE", "_LOAD_DATE"])
        seleccion = ", ".join(f"t.${i}" for i in range(1, len(COLUMNAS_RAW) + 3))
        cur.execute("BEGIN")
        previas = cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE _LOAD_DATE = %s", (fecha,)).fetchone()[0]
        if previas:
            log(f"{fecha} ya tenía {previas} filas: se reemplazan (carga idempotente).")
            cur.execute(f"DELETE FROM {TABLA} WHERE _LOAD_DATE = %s", (fecha,))
        cur.execute(f"""
            COPY INTO {TABLA} ({lista})
            FROM (SELECT {seleccion} FROM @{STAGE}/{fecha}/ t)
            FILE_FORMAT = ({FORMATO})
            FORCE = TRUE ON_ERROR = ABORT_STATEMENT""")
        cargadas = cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE _LOAD_DATE = %s", (fecha,)).fetchone()[0]
        if cargadas != esperadas:
            cur.execute("ROLLBACK")
            raise RuntimeError(f"{fecha}: se cargaron {cargadas} filas y el archivo tiene {esperadas}")
        cur.execute("COMMIT")
        log(f"{fecha}: {cargadas} filas cargadas en {TABLA} (archivo: {esperadas}).")
        return cargadas
    finally:
        con.close()


def simular_falla_si_corresponde() -> None:
    """Demostración del retry: falla solo en el primer intento de la ejecución."""
    if os.environ.get("SIMULAR_FALLA", "false").lower() != "true":
        return
    marca = DATOS / f".falla_simulada_{os.environ.get('EJECUCION_ID', 'manual')}"
    if not marca.exists():
        marca.write_text("1")
        raise RuntimeError("Falla simulada en el primer intento (demostración del retry)")
    log("Falla simulada ya ocurrió en un intento anterior: este intento continúa.")


def cargar_con_reintentos(fecha: str, forzar: bool, intentos: int = 3) -> int:
    """Reintento por día (fallas transitorias de Snowflake o de red), con espera creciente."""
    simular = os.environ.get("SIMULAR_FALLA_DIA", "").strip()
    for k in range(1, intentos + 1):
        try:
            if fecha == simular and k == 1:      # demostración del reintento por día
                raise RuntimeError(f"Falla simulada en el primer intento de {fecha} (SIMULAR_FALLA_DIA)")
            return cargar_fecha(fecha, forzar)
        except Exception as e:  # noqa: BLE001
            if k == intentos:
                raise
            log(f"{fecha}: intento {k} falló ({type(e).__name__}: {str(e)[:120]}); reintento en {5 * k} s")
            time.sleep(5 * k)
    return 0


def main() -> int:
    """Una fecha (FECHA) o un rango (FECHA_INICIO..FECHA_FIN), cargado en paralelo (CONCURRENCIA)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import date, timedelta

    inicio = os.environ.get("FECHA_INICIO") or os.environ["FECHA"]
    fin = os.environ.get("FECHA_FIN") or inicio
    for f in (inicio, fin):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", f):
            raise ValueError(f"Fecha inválida: {f!r}")
    forzar = os.environ.get("FORZAR", "true").lower() == "true"
    hilos = max(1, int(os.environ.get("CONCURRENCIA", "8")))
    d0, d1 = date.fromisoformat(inicio), date.fromisoformat(fin)
    fechas = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    log(f"Ingesta de {len(fechas)} fecha(s): {inicio} a {fin} | concurrencia {hilos} | forzar={forzar}")
    simular_falla_si_corresponde()
    preparar_fuente()
    con = conectar()                              # tabla y stage una sola vez, antes de los hilos
    try:
        crear_objetos(con.cursor())
    finally:
        con.close()
    t0, total, fallidas = time.time(), 0, []
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        futuros = {ex.submit(cargar_con_reintentos, f, forzar): f for f in fechas}
        for fut in as_completed(futuros):
            try:
                total += fut.result()
            except Exception as e:  # noqa: BLE001
                fallidas.append(futuros[fut])
                log(f"ERROR {futuros[fut]}: {type(e).__name__}: {str(e)[:200]}")
    log(f"RESUMEN: {len(fechas) - len(fallidas)}/{len(fechas)} fechas OK, {total} filas en RAW para el rango, "
        f"{time.time() - t0:.0f} s")
    if fallidas:
        raise RuntimeError(f"{len(fallidas)} fecha(s) fallaron tras sus reintentos: {sorted(fallidas)[:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
