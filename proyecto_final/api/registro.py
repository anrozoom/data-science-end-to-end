"""Registro de cada predicción y de cada solicitud en Snowflake, sin sumar latencia a la respuesta.

La API encola las filas y un hilo en segundo plano las escribe por microlotes (cada FLUSH_SEGUNDOS o cada
FLUSH_FILAS filas) con write_pandas. Tablas en CENTINELA.PRODUCCION:
  PREDICCIONES  una fila por predicción: id, timestamp, entradas (JSON), salida, decisión, versión, run_id,
                respaldo y latencia en ms -> trazable hasta la versión del modelo que la produjo.
  SOLICITUDES   una fila por solicitud HTTP (incluidos 4xx/5xx): ruta, código y latencia -> métricas de sistema.
Si REGISTRO_SNOWFLAKE=false (pruebas, CI) no se conecta a nada.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from pathlib import Path

import pandas as pd

log = logging.getLogger("centinela.registro")

DDL = {
    "PREDICCIONES": """CREATE TABLE IF NOT EXISTS {db}.PRODUCCION.PREDICCIONES (
        ID_PREDICCION VARCHAR, TS_UTC TIMESTAMP_NTZ, TRANS_NUM VARCHAR, LOTE NUMBER, ORIGEN VARCHAR,
        ENTRADAS VARCHAR, PROBABILIDAD FLOAT, DECISION VARCHAR, UMBRAL_VERIFICAR FLOAT, UMBRAL_RETENER FLOAT,
        MODELO_NOMBRE VARCHAR, MODELO_VERSION VARCHAR, MODELO_ALIAS VARCHAR, RUN_ID VARCHAR,
        RESPALDO BOOLEAN, MOTIVO_RESPALDO VARCHAR, LATENCIA_MS FLOAT)""",
    "SOLICITUDES": """CREATE TABLE IF NOT EXISTS {db}.PRODUCCION.SOLICITUDES (
        TS_UTC TIMESTAMP_NTZ, RUTA VARCHAR, METODO VARCHAR, CODIGO_HTTP NUMBER, LATENCIA_MS FLOAT,
        N_PREDICCIONES NUMBER, LOTE NUMBER)""",
}


class RegistroSnowflake:
    def __init__(self) -> None:
        self.activo = os.environ.get("REGISTRO_SNOWFLAKE", "true").lower() == "true"
        self.flush_segundos = float(os.environ.get("FLUSH_SEGUNDOS", "3"))
        self.flush_filas = int(os.environ.get("FLUSH_FILAS", "5000"))
        self.colas = {t: queue.Queue() for t in DDL}
        self.escritas = {t: 0 for t in DDL}
        self.errores = 0
        self._con = None
        if self.activo:
            threading.Thread(target=self._bucle, daemon=True, name="registro-snowflake").start()

    # --------------------------------------------------------------- API pública
    def predicciones(self, filas: list[dict]) -> None:
        if self.activo:
            for f in filas:
                f = dict(f)
                f["ENTRADAS"] = json.dumps(f.get("ENTRADAS"), ensure_ascii=False, default=str)
                self.colas["PREDICCIONES"].put(f)

    def solicitud(self, fila: dict) -> None:
        if self.activo:
            self.colas["SOLICITUDES"].put(fila)

    def estado(self) -> dict:
        return {"activo": self.activo, "pendientes": {t: q.qsize() for t, q in self.colas.items()},
                "escritas": dict(self.escritas), "errores": self.errores}

    def vaciar(self, timeout: float = 30) -> None:
        """Escribe lo pendiente (se usa al apagar y en las pruebas)."""
        fin = time.time() + timeout
        while self.activo and any(q.qsize() for q in self.colas.values()) and time.time() < fin:
            self._escribir()

    # ------------------------------------------------------------------ interno
    def _conectar(self):
        if self._con is None or self._con.is_closed():
            import snowflake.connector
            self._con = snowflake.connector.connect(
                account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
                role=os.environ["SNOWFLAKE_ROLE"], warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
                database=os.environ["SNOWFLAKE_DATABASE"], schema="PRODUCCION", authenticator="SNOWFLAKE_JWT",
                private_key_file=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", "/secrets/snowflake_key.p8"),
                private_key_file_pwd=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
                client_session_keep_alive=True)
            cur = self._con.cursor()
            for ddl in DDL.values():
                cur.execute(ddl.format(db=os.environ["SNOWFLAKE_DATABASE"]))
        return self._con

    def _escribir(self) -> None:
        from snowflake.connector.pandas_tools import write_pandas
        for tabla, cola in self.colas.items():
            filas = []
            while not cola.empty() and len(filas) < 50_000:
                filas.append(cola.get_nowait())
            if not filas:
                continue
            try:
                df = pd.DataFrame(filas)
                ok, _, n, _ = write_pandas(self._conectar(), df, tabla, schema="PRODUCCION",
                                           quote_identifiers=False, use_logical_type=True)
                self.escritas[tabla] += int(n) if ok else 0
            except Exception as e:  # noqa: BLE001 - no tumbar la API por el registro; reintentar después
                self.errores += 1
                log.warning("No se pudo escribir %s filas en %s (%s); se reintentará", len(filas), tabla, e)
                for f in filas:
                    cola.put(f)
                self._con = None
                time.sleep(5)

    def _bucle(self) -> None:
        ultimo = time.time()
        while True:
            time.sleep(0.5)
            listo = any(q.qsize() >= self.flush_filas for q in self.colas.values())
            if listo or (time.time() - ultimo >= self.flush_segundos and any(q.qsize() for q in self.colas.values())):
                self._escribir()
                ultimo = time.time()
