"""Contrato de la API de Centinela (Pydantic), igual a la firma registrada en MLflow para centinela-modelo.

La firma tiene 21 entradas. Aquí se validan:
- tipos: double -> float, integer -> int, boolean -> bool, string -> categoría cerrada;
- rangos de VALIDEZ del dominio (no los mínimos y máximos del entrenamiento, para no rechazar valores
  legítimos nuevos): montos > 0 o >= 0, hora 0-23, día 1-7, edad 10-110, distancia <= 20.016 km;
- categorías permitidas: las vistas en entrenamiento (api/catalogos.json). Una categoría nueva es 422.
- campos desconocidos: rechazados (extra="forbid"), para que un nombre mal escrito no pase en silencio.
monto_medio_previo, monto_relativo y segundos_desde_anterior son opcionales (nulos en la primera compra
del cliente), igual que en la firma (required: False).
"""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CATALOGOS = json.loads((Path(__file__).resolve().parent / "catalogos.json").read_text(encoding="utf-8"))

Categoria = Enum("Categoria", {c: c for c in CATALOGOS["categoria"]}, type=str)
Canal = Enum("Canal", {c: c for c in CATALOGOS["canal"]}, type=str)
Estado = Enum("Estado", {c: c for c in CATALOGOS["state"]}, type=str)

# Orden exacto de las columnas de la firma del modelo.
COLUMNAS_MODELO = ["amt", "distancia_km", "edad_en_transaccion", "city_pop", "n_tx_1h", "gasto_1h", "n_tx_24h",
                   "gasto_24h", "n_tx_previas", "monto_medio_previo", "monto_relativo", "hora", "dia_semana",
                   "es_nocturna", "es_fin_de_semana", "es_menor_de_edad", "es_multicategoria", "categoria", "canal",
                   "state", "segundos_desde_anterior"]


class Transaccion(BaseModel):
    """Una transacción en el momento de la autorización (variables calculadas solo con el pasado)."""
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    trans_num: Optional[str] = Field(None, max_length=64, description="Id de la transacción (trazabilidad); no entra al modelo")
    amt: float = Field(..., gt=0, le=1_000_000, description="Monto en USD")
    distancia_km: float = Field(..., ge=0, le=20_016, description="Distancia cliente-comercio (haversine)")
    edad_en_transaccion: int = Field(..., ge=10, le=110)
    city_pop: int = Field(..., ge=0)
    n_tx_1h: int = Field(..., ge=0, description="Transacciones del cliente en la hora previa")
    gasto_1h: float = Field(..., ge=0)
    n_tx_24h: int = Field(..., ge=0)
    gasto_24h: float = Field(..., ge=0)
    n_tx_previas: int = Field(..., ge=0)
    monto_medio_previo: Optional[float] = Field(None, ge=0, description="Nulo en la primera compra del cliente")
    monto_relativo: Optional[float] = Field(None, ge=0)
    hora: int = Field(..., ge=0, le=23)
    dia_semana: int = Field(..., ge=1, le=7, description="1 = lunes")
    es_nocturna: bool
    es_fin_de_semana: bool
    es_menor_de_edad: bool
    es_multicategoria: bool
    categoria: Categoria
    canal: Canal
    state: Estado
    segundos_desde_anterior: Optional[float] = Field(None, ge=0)


class Lote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lote: Optional[int] = Field(None, ge=0, description="Número de lote de la simulación (trazabilidad)")
    transacciones: list[Transaccion] = Field(..., min_length=1, max_length=50_000)


Decision = Literal["aprobar", "verificar", "retener"]


class Prediccion(BaseModel):
    id_prediccion: str
    trans_num: Optional[str] = None
    probabilidad: Optional[float] = Field(None, description="Puntaje del modelo; nulo en modo de respaldo")
    decision: Decision
    umbral_verificar: Optional[float] = None
    umbral_retener: Optional[float] = None
    modelo: str
    version_modelo: Optional[str] = None
    alias: Optional[str] = None
    run_id: Optional[str] = None
    respaldo: bool
    motivo_respaldo: Optional[str] = None
    latencia_ms: float
    timestamp_utc: datetime


class RespuestaLote(BaseModel):
    lote: Optional[int]
    n: int
    respaldo: bool
    version_modelo: Optional[str]
    latencia_ms: float
    predicciones: list[Prediccion]
