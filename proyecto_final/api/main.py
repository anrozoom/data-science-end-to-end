"""API de inferencia de Centinela (FastAPI).

Endpoints:
  GET  /salud           estado del servicio y si el modelo cargó
  GET  /modelo          nombre, versión, alias, run_id y umbrales del modelo en uso
  POST /predecir        una transacción -> probabilidad, decisión (aprobar / verificar / retener), versión, id
  POST /predecir_lote   varias transacciones (tráfico simulado); cada fila queda como predicción individual
  POST /recargar        (protegido) vuelve a resolver el alias ahora, sin esperar la recarga periódica
  POST /respaldo        (protegido) interruptor: fuerza o quita el modo de respaldo (reglas fijas del PSet 1)
  GET  /metricas        contadores en memoria: solicitudes por código HTTP y latencias

Modelo: MODELO_URI (por defecto models:/centinela-modelo@champion). Un hilo vuelve a resolver el alias cada
RECARGA_SEGUNDOS y carga la versión nueva si cambió: mover el alias en MLflow cambia el modelo SIN
reconstruir la imagen (rollback incluido). Si el modelo no carga, la API responde con las reglas fijas del
PSet 1 e indica "respaldo": true. Umbrales: tags umbral_decision (verificar) y umbral_retener de la versión.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from esquemas import CATALOGOS, COLUMNAS_MODELO, Lote, Prediccion, RespuestaLote, Transaccion
from registro import RegistroSnowflake

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("centinela.api")

MODELO_URI = os.environ.get("MODELO_URI", "models:/centinela-modelo@champion")
RECARGA_SEGUNDOS = float(os.environ.get("RECARGA_SEGUNDOS", "30"))
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
UMBRAL_VERIFICAR_DEFECTO = float(os.environ.get("UMBRAL_VERIFICAR", "0.24"))
UMBRAL_RETENER_DEFECTO = float(os.environ.get("UMBRAL_RETENER", "0.85"))


def ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------- reglas (respaldo)
def reglas_fijas(df: pd.DataFrame) -> np.ndarray:
    """Reglas actuales del banco (PSet 1), con el p95 por categoría aprendido en entrenamiento."""
    p95 = df["categoria"].map(CATALOGOS["p95_amt_por_categoria"]).astype(float).fillna(np.inf)
    return ((df["amt"] > p95)
            | (df["es_nocturna"].astype(bool) & (df["amt"] >= CATALOGOS["regla_monto_minimo_nocturno"]))
            | (df["distancia_km"] > CATALOGOS["regla_distancia_km"])).to_numpy()


# ------------------------------------------------------------------------------ gestor del modelo
class GestorModelo:
    def __init__(self, uri: str) -> None:
        self.uri = uri
        self.modelo = None
        self.info: dict = {}
        self.error: Optional[str] = None
        self.forzar_respaldo = os.environ.get("MODO_RESPALDO", "false").lower() == "true"
        self._lock = threading.Lock()

    @property
    def respaldo(self) -> bool:
        return self.forzar_respaldo or self.modelo is None

    @property
    def motivo_respaldo(self) -> Optional[str]:
        if self.forzar_respaldo:
            return "interruptor de respaldo activado"
        if self.modelo is None:
            return f"modelo no cargado: {self.error}"
        return None

    def cargar(self) -> bool:
        """Resuelve el alias y carga la versión si cambió. Devuelve True si cambió el modelo en uso."""
        import mlflow
        try:
            if self.uri.startswith("models:/") and "@" in self.uri:
                from mlflow import MlflowClient
                nombre, alias = self.uri[len("models:/"):].split("@", 1)
                v = MlflowClient().get_model_version_by_alias(nombre, alias)
                if self.modelo is not None and self.info.get("version") == v.version:
                    self.error = None
                    return False
                modelo = mlflow.sklearn.load_model(f"models:/{nombre}/{v.version}")
                info = {"nombre": nombre, "alias": alias, "version": v.version, "run_id": v.run_id,
                        "umbral_verificar": float(v.tags.get("umbral_decision", UMBRAL_VERIFICAR_DEFECTO)),
                        "umbral_retener": float(v.tags.get("umbral_retener", UMBRAL_RETENER_DEFECTO))}
            else:                                    # ruta local (CI: modelo exportado con save_model)
                if self.modelo is not None:
                    return False
                modelo = mlflow.sklearn.load_model(self.uri)
                meta = Path(self.uri) / "info_modelo.json"
                extra = json.loads(meta.read_text()) if meta.exists() else {}
                info = {"nombre": extra.get("nombre", "centinela-modelo"), "alias": extra.get("alias"),
                        "version": extra.get("version"), "run_id": extra.get("run_id"),
                        "umbral_verificar": float(extra.get("umbral_verificar", UMBRAL_VERIFICAR_DEFECTO)),
                        "umbral_retener": float(extra.get("umbral_retener", UMBRAL_RETENER_DEFECTO))}
            info["cargado_utc"] = ahora().isoformat()
            with self._lock:
                anterior = self.info.get("version")
                self.modelo, self.info, self.error = modelo, info, None
            log.info("Modelo en uso: %s versión %s (antes: %s)", info["nombre"], info["version"], anterior)
            return True
        except Exception as e:  # noqa: BLE001 - se conserva el modelo anterior; sin modelo -> respaldo
            self.error = f"{type(e).__name__}: {str(e)[:200]}"
            log.warning("No se pudo cargar %s: %s", self.uri, self.error)
            return False

    def predecir(self, df: pd.DataFrame) -> tuple[Optional[np.ndarray], list[str], dict]:
        with self._lock:
            modelo, info, respaldo, motivo = self.modelo, dict(self.info), self.respaldo, self.motivo_respaldo
        if respaldo:
            alerta = reglas_fijas(df)
            return None, np.where(alerta, "verificar", "aprobar").tolist(), {**info, "respaldo": True, "motivo": motivo}
        p = modelo.predict_proba(df[COLUMNAS_MODELO])[:, 1]
        dec = np.where(p >= info["umbral_retener"], "retener", np.where(p >= info["umbral_verificar"], "verificar", "aprobar"))
        return p, dec.tolist(), {**info, "respaldo": False, "motivo": None}

    def bucle(self) -> None:
        while True:
            time.sleep(RECARGA_SEGUNDOS)
            self.cargar()


gestor = GestorModelo(MODELO_URI)
registro = RegistroSnowflake()
METRICAS = {"inicio_utc": ahora().isoformat(), "por_codigo": {}, "latencias_ms": []}


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    gestor.cargar()
    threading.Thread(target=gestor.bucle, daemon=True, name="recarga-alias").start()
    yield
    registro.vaciar()


app = FastAPI(title="Centinela · API de riesgo de fraude", version="1.0", lifespan=ciclo_de_vida)


# ------------------------------------------------------------------------------- middleware y errores
@app.middleware("http")
async def medir(request: Request, call_next):
    t0 = time.perf_counter()
    respuesta = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    codigo = respuesta.status_code
    METRICAS["por_codigo"][str(codigo)] = METRICAS["por_codigo"].get(str(codigo), 0) + 1
    if request.url.path.startswith("/predecir"):
        METRICAS["latencias_ms"] = (METRICAS["latencias_ms"] + [ms])[-10_000:]
        registro.solicitud({"TS_UTC": ahora(), "RUTA": request.url.path, "METODO": request.method,
                            "CODIGO_HTTP": codigo, "LATENCIA_MS": ms,
                            "N_PREDICCIONES": int(respuesta.headers.get("x-n-predicciones", 0)),
                            "LOTE": int(respuesta.headers["x-lote"]) if respuesta.headers.get("x-lote") else None})
    return respuesta


@app.exception_handler(RequestValidationError)
async def entrada_invalida(request: Request, exc: RequestValidationError):
    errores = [{"campo": ".".join(str(x) for x in e["loc"][1:]) or "cuerpo", "error": e["msg"], "tipo": e["type"]}
               for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "mensaje": "Entrada inválida: " + "; ".join(f"campo '{e['campo']}': {e['error']}" for e in errores[:5]),
        "errores": errores})


def _token(x_token: Optional[str]) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(503, "Endpoint protegido deshabilitado: falta ADMIN_TOKEN en el servidor")
    if x_token != ADMIN_TOKEN:
        raise HTTPException(401, "Token inválido (cabecera X-Token)")


# ------------------------------------------------------------------------------------- endpoints
@app.get("/salud")
def salud():
    return {"estado": "ok", "modelo_cargado": gestor.modelo is not None, "respaldo": gestor.respaldo,
            "motivo_respaldo": gestor.motivo_respaldo, "version_modelo": gestor.info.get("version"),
            "registro_snowflake": registro.estado()}


@app.get("/modelo")
def modelo():
    return {"uri": gestor.uri, **gestor.info, "respaldo": gestor.respaldo, "motivo_respaldo": gestor.motivo_respaldo,
            "recarga_cada_segundos": RECARGA_SEGUNDOS}


def _responder(transacciones: list[Transaccion], lote: Optional[int], origen: str) -> tuple[list[Prediccion], float, dict]:
    df = pd.DataFrame([t.model_dump() for t in transacciones])
    t0 = time.perf_counter()
    p, decisiones, info = gestor.predecir(df)
    ms_total = (time.perf_counter() - t0) * 1000
    ms_fila = ms_total / len(df)
    ts = ahora()
    salida, filas = [], []
    for i, t in enumerate(transacciones):
        pid = str(uuid.uuid4())
        prob = None if p is None else float(p[i])
        salida.append(Prediccion(
            id_prediccion=pid, trans_num=t.trans_num, probabilidad=prob, decision=decisiones[i],
            umbral_verificar=info.get("umbral_verificar"), umbral_retener=info.get("umbral_retener"),
            modelo=info.get("nombre", "reglas_fijas_pset1") if not info["respaldo"] else "reglas_fijas_pset1",
            version_modelo=info.get("version"), alias=info.get("alias"), run_id=info.get("run_id"),
            respaldo=info["respaldo"], motivo_respaldo=info["motivo"], latencia_ms=round(ms_fila, 3), timestamp_utc=ts))
        filas.append({"ID_PREDICCION": pid, "TS_UTC": ts, "TRANS_NUM": t.trans_num, "LOTE": lote, "ORIGEN": origen,
                      "ENTRADAS": t.model_dump(exclude={"trans_num"}), "PROBABILIDAD": prob, "DECISION": decisiones[i],
                      "UMBRAL_VERIFICAR": info.get("umbral_verificar"), "UMBRAL_RETENER": info.get("umbral_retener"),
                      "MODELO_NOMBRE": "reglas_fijas_pset1" if info["respaldo"] else info.get("nombre"),
                      "MODELO_VERSION": info.get("version"), "MODELO_ALIAS": info.get("alias"),
                      "RUN_ID": info.get("run_id"), "RESPALDO": info["respaldo"], "MOTIVO_RESPALDO": info["motivo"],
                      "LATENCIA_MS": ms_fila})
    registro.predicciones(filas)
    return salida, ms_total, info


@app.post("/predecir", response_model=Prediccion)
def predecir(transaccion: Transaccion, lote: Optional[int] = None):
    salida, _, _ = _responder([transaccion], lote, "online")
    headers = {"x-n-predicciones": "1", **({"x-lote": str(lote)} if lote is not None else {})}
    return JSONResponse(content=json.loads(salida[0].model_dump_json()), headers=headers)


@app.post("/predecir_lote", response_model=RespuestaLote)
def predecir_lote(entrada: Lote):
    salida, ms, info = _responder(entrada.transacciones, entrada.lote, "lote")
    cuerpo = RespuestaLote(lote=entrada.lote, n=len(salida), respaldo=info["respaldo"], version_modelo=info.get("version"),
                           latencia_ms=round(ms, 3), predicciones=salida)
    headers = {"x-n-predicciones": str(len(salida)), **({"x-lote": str(entrada.lote)} if entrada.lote is not None else {})}
    return JSONResponse(content=json.loads(cuerpo.model_dump_json()), headers=headers)


class Interruptor(BaseModel):
    activo: bool


@app.post("/respaldo")
def respaldo(cuerpo: Interruptor, x_token: Optional[str] = Header(None)):
    _token(x_token)
    gestor.forzar_respaldo = cuerpo.activo
    log.warning("Interruptor de respaldo: %s", "ACTIVADO" if cuerpo.activo else "desactivado")
    return {"respaldo": gestor.respaldo, "motivo_respaldo": gestor.motivo_respaldo}


@app.post("/recargar")
def recargar(x_token: Optional[str] = Header(None)):
    _token(x_token)
    cambio = gestor.cargar()
    return {"cambio": cambio, **gestor.info, "error": gestor.error}


@app.get("/metricas")
def metricas():
    lat = np.array(METRICAS["latencias_ms"]) if METRICAS["latencias_ms"] else np.array([np.nan])
    return {"inicio_utc": METRICAS["inicio_utc"], "solicitudes_por_codigo": METRICAS["por_codigo"],
            "latencia_ms_p50": float(np.nanpercentile(lat, 50)), "latencia_ms_p95": float(np.nanpercentile(lat, 95)),
            "registro_snowflake": registro.estado()}
