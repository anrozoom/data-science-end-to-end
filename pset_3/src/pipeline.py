"""Preparación, validación y métricas del modelo de fraude de Centinela.

Los notebooks importan este módulo (no copian su código):
    from pipeline import dividir, construir_modelo, CVTemporalSubmuestreada, evaluar_cv, ...

Decisiones (justificadas en los notebooks 01-02 y en pset_3/docs/):
- Hold-out = partición temporal de prueba del PSet 1 (jul-dic 2020), usada UNA vez al final.
- CV en entrenamiento: TimeSeriesSplit(3) sobre las filas ordenadas por tiempo. En cada
  pliegue se AJUSTA con todos los fraudes y una fracción de las legítimas (cómputo), y se
  VALIDA con todas las filas del pliegue de validación (prevalencia real).
- Toda la preparación (imputación, codificación, escalado y el percentil 95 por categoría)
  vive dentro de un Pipeline + ColumnTransformer ajustado solo con entrenamiento.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEMILLA = 42
OBJETIVO = "is_fraud"
COSTO_FALSA_ALARMA = 5.0          # USD por falsa alarma (supuesto del PSet 1)
FRACCION_LEGITIMAS = 0.05         # fracción de legítimas que se usa para AJUSTAR (no para validar)

# Columnas de la OBT que NO entran al modelo, con su motivo (fuga o no disponibles/útiles).
EXCLUIDAS = {
    "trans_num": "identificador de la transacción",
    "trans_ts": "marca de tiempo: se usa solo para ordenar y dividir",
    "fecha": "fecha calendario: el modelo debe generalizar a fechas futuras",
    "anio": "año: no se repite en el futuro (2019/2020)",
    "mes": "mes: prueba (jul-dic) y entrenamiento cubren meses distintos del ciclo",
    "particion_temporal": "define la división entrenamiento/prueba",
    "source_file": "archivo de origen de Kaggle: correlaciona con la partición, no con el fraude",
    "cliente_sk": "identificador del cliente (memorizaría clientes)",
    "comercio_sk": "identificador del comercio",
    "categoria_sk": "clave sustituta (la categoría entra como texto)",
    "comercio": "693 valores: alta cardinalidad, identificaría comercios del dataset simulado",
    "job": "497 valores: alta cardinalidad y atributo personal",
    "gender": "atributo sensible: se excluye por equidad",
    "cliente_lat": "coordenada cruda (identifica al cliente); se usa vía distancia_km",
    "cliente_long": "coordenada cruda; se usa vía distancia_km",
    "merch_lat": "coordenada cruda; se usa vía distancia_km",
    "merch_long": "coordenada cruda; se usa vía distancia_km",
    "franja": "redundante con hora",
}

# Variables de la OBT (todas calculadas solo con el pasado o con la propia transacción).
NUMERICAS_OBT = ["amt", "distancia_km", "edad_en_transaccion", "city_pop", "n_tx_1h", "gasto_1h",
                 "n_tx_24h", "gasto_24h", "n_tx_previas", "monto_medio_previo", "monto_relativo",
                 "hora", "dia_semana"]
BINARIAS = ["es_nocturna", "es_fin_de_semana", "es_menor_de_edad", "es_multicategoria"]
CATEGORICAS = ["categoria", "canal", "state"]
# Features derivadas en este PSet (ver 02_features.ipynb).
DERIVADAS = ["log_amt", "hora_sin", "hora_cos", "log_segundos_desde_anterior"]
NUMERICAS = NUMERICAS_OBT + DERIVADAS
ENTRADA = NUMERICAS_OBT + BINARIAS + CATEGORICAS + ["segundos_desde_anterior"]


# ----------------------------------------------------------------------------- features
def agregar_features(X: pd.DataFrame) -> pd.DataFrame:
    """Features derivadas sin estado: solo usan columnas de la propia transacción."""
    X = X.copy()
    X["log_amt"] = np.log1p(X["amt"].astype(float))
    angulo = 2 * np.pi * X["hora"].astype(float) / 24
    X["hora_sin"] = np.sin(angulo)
    X["hora_cos"] = np.cos(angulo)
    X["log_segundos_desde_anterior"] = np.log1p(X["segundos_desde_anterior"].astype(float))
    for c in BINARIAS:
        X[c] = X[c].astype(float)
    return X


class MontoSobreP95Categoria(BaseEstimator, TransformerMixin):
    """amt / percentil 95 del monto de su categoría, con el p95 aprendido SOLO en el fit.

    Feature derivada de la EDA: el fraude se concentra en montos altos *para su categoría*
    (la regla fija del banco usa ese mismo p95). Categorías nuevas usan el p95 global.
    """

    def __init__(self, percentil: float = 95):
        self.percentil = percentil

    def fit(self, X, y=None):
        X = pd.DataFrame(X, columns=["amt", "categoria"])
        self.p95_ = X.groupby("categoria")["amt"].quantile(self.percentil / 100).astype(float).to_dict()
        self.p95_global_ = float(np.percentile(X["amt"].astype(float), self.percentil))
        return self

    def transform(self, X):
        X = pd.DataFrame(X, columns=["amt", "categoria"])
        ref = X["categoria"].map(self.p95_).astype(float).fillna(self.p95_global_)
        return (X["amt"].astype(float) / ref).to_numpy().reshape(-1, 1)

    def get_feature_names_out(self, input_features=None):
        return np.array(["amt_sobre_p95_categoria"])


TODAS_DERIVADAS = ("log_amt", "hora_ciclica", "log_segundos_desde_anterior", "amt_sobre_p95_categoria")
# Features que se quedan tras la ablación pareada de 02_features.ipynb: la hora cíclica no
# mejoró en ningún modelo (hora y es_nocturna ya capturan la señal) y se descarta.
DERIVADAS_FINALES = ("log_amt", "log_segundos_desde_anterior", "amt_sobre_p95_categoria")


def construir_preparacion(derivadas=DERIVADAS_FINALES) -> Pipeline:
    """Preparación completa. `derivadas` permite quitar features derivadas (ablación en 02)."""
    numericas = list(NUMERICAS_OBT)
    if "log_amt" in derivadas:
        numericas.append("log_amt")
    if "hora_ciclica" in derivadas:
        numericas += ["hora_sin", "hora_cos"]
    if "log_segundos_desde_anterior" in derivadas:
        numericas.append("log_segundos_desde_anterior")
    bloques = [
        ("numericas", Pipeline([
            # monto_relativo y segundos_desde_anterior son nulos en la 1.a compra del cliente:
            # mediana + indicador de faltante.
            ("imputar", SimpleImputer(strategy="median", add_indicator=True)),
            ("escalar", StandardScaler()),
        ]), numericas),
        ("binarias", SimpleImputer(strategy="most_frequent"), BINARIAS),
        ("categoricas", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAS),
    ]
    if "amt_sobre_p95_categoria" in derivadas:
        bloques.append(("monto_p95_categoria", Pipeline([
            ("p95", MontoSobreP95Categoria()),
            ("escalar", StandardScaler()),
        ]), ["amt", "categoria"]))
    columnas = ColumnTransformer(bloques, verbose_feature_names_out=False)
    return Pipeline([("features", _FeaturesDerivadas()), ("columnas", columnas)])


class _FeaturesDerivadas(BaseEstimator, TransformerMixin):
    """Envuelve agregar_features para que viva dentro del Pipeline (sin estado)."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return agregar_features(pd.DataFrame(X))

    def get_feature_names_out(self, input_features=None):
        base = list(input_features) if input_features is not None else list(ENTRADA)
        return np.array(base + [c for c in DERIVADAS if c not in base])


def construir_modelo(estimador, derivadas=DERIVADAS_FINALES) -> Pipeline:
    return Pipeline([("preparacion", construir_preparacion(derivadas)), ("modelo", estimador)])


# ------------------------------------------------------------------------ división y CV
def dividir(df: pd.DataFrame):
    """Divide UNA vez por la partición temporal del PSet 1. Filas ordenadas por tiempo."""
    df = df.sort_values(["trans_ts", "trans_num"]).reset_index(drop=True)
    ent = df[df["particion_temporal"] == "entrenamiento"].reset_index(drop=True)
    pru = df[df["particion_temporal"] == "prueba"].reset_index(drop=True)
    return (ent[ENTRADA], ent[OBJETIVO].astype(int), pru[ENTRADA], pru[OBJETIVO].astype(int),
            ent, pru)


class CVTemporalSubmuestreada:
    """TimeSeriesSplit cuyo bloque de ajuste conserva todos los fraudes y una fracción de
    las legítimas; el bloque de validación queda completo (prevalencia real)."""

    def __init__(self, n_splits: int = 3, fraccion_legitimas: float = FRACCION_LEGITIMAS,
                 semilla: int = SEMILLA):
        self.n_splits = n_splits
        self.fraccion_legitimas = fraccion_legitimas
        self.semilla = semilla

    def split(self, X, y, groups=None):
        y = np.asarray(y)
        for k, (ajuste, valid) in enumerate(TimeSeriesSplit(n_splits=self.n_splits).split(X)):
            yield submuestrear(ajuste, y, self.fraccion_legitimas, self.semilla + k), valid

    def get_n_splits(self, X=None, y=None, groups=None):
        return self.n_splits


def submuestrear(indices, y, fraccion, semilla):
    """Todos los fraudes + una fracción aleatoria (fija por semilla) de las legítimas."""
    indices = np.asarray(indices)
    rng = np.random.default_rng(semilla)
    pos = indices[y[indices] == 1]
    neg = indices[y[indices] == 0]
    neg = rng.choice(neg, size=int(round(len(neg) * fraccion)), replace=False)
    return np.sort(np.concatenate([pos, neg]))


def pesos_prevalencia_real(y_sub, fraccion):
    """Pesos que devuelven un bloque submuestreado a la prevalencia real (legítimas 1/f)."""
    return np.where(np.asarray(y_sub) == 1, 1.0, 1.0 / fraccion)


# ----------------------------------------------------------------------------- métricas
def auc_pr(y, score, sample_weight=None) -> float:
    return float(average_precision_score(y, score, sample_weight=sample_weight))


def perdida_neta(y, score, monto, umbral) -> float:
    """Monto de fraude no detectado + USD 5 por cada falsa alarma (métrica de negocio)."""
    y, score, monto = np.asarray(y), np.asarray(score), np.asarray(monto, dtype=float)
    alerta = score >= umbral
    return float(monto[(y == 1) & ~alerta].sum() + COSTO_FALSA_ALARMA * ((y == 0) & alerta).sum())


def umbral_optimo(y, score, monto):
    """Umbral que minimiza la pérdida neta, recorriendo todos los cortes posibles (O(n log n))."""
    y, score, monto = np.asarray(y), np.asarray(score, dtype=float), np.asarray(monto, dtype=float)
    orden = np.argsort(-score, kind="mergesort")
    s, yy, mm = score[orden], y[orden], monto[orden]
    fraude_total = mm[yy == 1].sum()
    capturado = np.cumsum(np.where(yy == 1, mm, 0.0))
    falsas = np.cumsum(yy == 0)
    perdida = fraude_total - capturado + COSTO_FALSA_ALARMA * falsas
    # solo cortes donde cambia el score (umbral = score de la última fila alertada)
    ultimo = np.r_[s[1:] != s[:-1], True]
    perdida_c = np.where(ultimo, perdida, np.inf)
    k = int(np.argmin(perdida_c))
    if fraude_total <= perdida_c[k]:          # no alertar nada es mejor
        return float(np.inf), float(fraude_total)
    return float(s[k]), float(perdida_c[k])


def resumen_negocio(y, score, monto, umbral) -> dict:
    y, score, monto = np.asarray(y), np.asarray(score), np.asarray(monto, dtype=float)
    alerta = score >= umbral
    return {
        "perdida_neta": perdida_neta(y, score, monto, umbral),
        "fraude_no_detectado_usd": float(monto[(y == 1) & ~alerta].sum()),
        "falsas_alarmas": int(((y == 0) & alerta).sum()),
        "fraudes_detectados": int(((y == 1) & alerta).sum()),
        "fraudes_totales": int((y == 1).sum()),
        "recall": float(((y == 1) & alerta).sum() / max((y == 1).sum(), 1)),
        "precision": float(((y == 1) & alerta).sum() / max(alerta.sum(), 1)),
        "pct_legitimas_alertadas": float(100 * ((y == 0) & alerta).sum() / max((y == 0).sum(), 1)),
    }


# -------------------------------------------------------------------- línea de negocio
class ReglasFijas(BaseEstimator, ClassifierMixin):
    """Reglas actuales del banco (PSet 1): alerta si se cumple al menos una.

    1. monto > percentil 95 del monto de su categoría (aprendido en el fit);
    2. compra nocturna (22:00-04:00) con monto >= monto_minimo_nocturno;
    3. comercio a más de distancia_km del domicilio del cliente.
    El "puntaje" es binario (0/1): no hay ranking más allá de la regla.
    """

    def __init__(self, monto_minimo_nocturno: float = 100.0, distancia_km: float = 100.0):
        self.monto_minimo_nocturno = monto_minimo_nocturno
        self.distancia_km = distancia_km

    def fit(self, X, y=None):
        X = pd.DataFrame(X)
        self.p95_ = X.groupby("categoria")["amt"].quantile(0.95).astype(float).to_dict()
        self.classes_ = np.array([0, 1])
        return self

    def _alerta(self, X):
        X = pd.DataFrame(X)
        amt = X["amt"].astype(float)
        p95 = X["categoria"].map(self.p95_).astype(float).fillna(np.inf)
        nocturna = X["es_nocturna"].astype(bool)
        return ((amt > p95) | (nocturna & (amt >= self.monto_minimo_nocturno))
                | (X["distancia_km"].astype(float) > self.distancia_km)).to_numpy()

    def predict_proba(self, X):
        a = self._alerta(X).astype(float)
        return np.column_stack([1 - a, a])

    def predict(self, X):
        return self._alerta(X).astype(int)


# ------------------------------------------------------------------------- evaluación
def evaluar_cv(estimador, X, y, cv: CVTemporalSubmuestreada, monto=None) -> dict:
    """CV temporal: AUC-PR de validación (prevalencia real) y de entrenamiento (ponderada a
    la prevalencia real, para que la brecha mida sobreajuste y no diferencia de prevalencia).
    Devuelve también las predicciones fuera de pliegue para elegir el umbral de negocio."""
    y = np.asarray(y)
    filas = []
    oof_idx, oof_score = [], []
    for k, (ajuste, valid) in enumerate(cv.split(X, y)):
        modelo = clone(estimador)
        t0 = time.perf_counter()
        modelo.fit(X.iloc[ajuste], y[ajuste])
        t_fit = time.perf_counter() - t0
        s_aj = modelo.predict_proba(X.iloc[ajuste])[:, 1]
        t0 = time.perf_counter()
        s_va = modelo.predict_proba(X.iloc[valid])[:, 1]
        t_pred = time.perf_counter() - t0
        filas.append({
            "pliegue": k,
            "auc_pr_entrenamiento": auc_pr(y[ajuste], s_aj, pesos_prevalencia_real(y[ajuste], cv.fraccion_legitimas)),
            "auc_pr_validacion": auc_pr(y[valid], s_va),
            "segundos_entrenamiento": t_fit,
            "segundos_prediccion": t_pred,
            "filas_ajuste": len(ajuste), "filas_validacion": len(valid),
        })
        oof_idx.append(valid)
        oof_score.append(s_va)
    p = pd.DataFrame(filas)
    oof_idx, oof_score = np.concatenate(oof_idx), np.concatenate(oof_score)
    res = {
        "pliegues": p,
        "cv_auc_pr_media": float(p["auc_pr_validacion"].mean()),
        "cv_auc_pr_std": float(p["auc_pr_validacion"].std(ddof=0)),
        "entrenamiento_auc_pr_media": float(p["auc_pr_entrenamiento"].mean()),
        "segundos_entrenamiento": float(p["segundos_entrenamiento"].sum()),
        "segundos_prediccion": float(p["segundos_prediccion"].sum()),
        "oof_indices": oof_idx,
        "oof_score": oof_score,
    }
    res["brecha_auc_pr"] = res["entrenamiento_auc_pr_media"] - res["cv_auc_pr_media"]
    if monto is not None:
        m = np.asarray(monto, dtype=float)
        umbral, perdida = umbral_optimo(y[oof_idx], oof_score, m[oof_idx])
        res["cv_umbral_optimo"] = umbral
        res["cv_perdida_neta_oof"] = perdida
    return res
