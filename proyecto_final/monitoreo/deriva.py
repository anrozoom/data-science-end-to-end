"""Deriva de datos: PSI por variable, con Kolmogorov-Smirnov (numéricas) y chi-cuadrado (categóricas) como respaldo.

PSI = sum((a - r) * ln(a / r)) sobre los tramos de la referencia (r) y del lote actual (a).
  - Numéricas: 10 tramos por cuantiles de la REFERENCIA + un tramo para los nulos.
  - Categóricas (y enteras de pocos valores, como la hora): un tramo por valor.
  - Las proporciones se recortan en 1e-4 para que un tramo vacío no dé infinito.
Umbrales estándar de la industria (Siddiqi, 2006; usados en riesgo de crédito): < 0,10 estable;
0,10 a 0,25 cambio moderado (aviso); >= 0,25 cambio importante (alerta).

KS y chi-cuadrado: con 10.000 a 30.000 filas por lote casi cualquier diferencia es "significativa"; se
reportan el estadístico y el valor p como complemento del diagnóstico, pero NO disparan alertas.

Referencia: la MISMA semana de 2019 (364 días antes, mismos días de la semana) de la partición de
entrenamiento, para no confundir la estacionalidad (diciembre duplica el volumen) con deriva.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

PSI_AVISO, PSI_ALERTA = 0.10, 0.25
EPS = 1e-4

NUMERICAS = ["amt", "distancia_km", "edad_en_transaccion", "city_pop", "n_tx_1h", "gasto_1h", "n_tx_24h",
             "gasto_24h", "monto_medio_previo", "monto_relativo", "segundos_desde_anterior"]
CATEGORICAS = ["hora", "categoria", "canal", "state", "es_nocturna", "es_menor_de_edad", "es_multicategoria"]
VIGILADAS = NUMERICAS + CATEGORICAS
# Variables de la firma que NO se vigilan con PSI (con la evidencia en docs/monitoreo/psi_natural.csv).
EXCLUIDAS = {
    "n_tx_previas": "contador acumulado del historial del cliente: crece por construcción con el tiempo, así "
                    "que su PSI contra cualquier referencia pasada es alto aunque la población no cambie",
    "dia_semana": "en un lote de 7 días cada día aparece una vez; su PSI solo mide cómo se reparte el volumen "
                  "entre los días (semanas de feriados), algo que ya vigila la alerta de volumen",
    "es_fin_de_semana": "se deriva de dia_semana (sábado o domingo) y hereda el mismo problema: mide el reparto "
                        "del volumen dentro de la semana, no un cambio de la población",
}


def _proporciones(conteos: np.ndarray) -> np.ndarray:
    total = conteos.sum()
    return np.clip(conteos / total if total else conteos, EPS, None)


def psi_numerica(ref: pd.Series, act: pd.Series, n_tramos: int = 10) -> float:
    r = pd.to_numeric(ref, errors="coerce").to_numpy(dtype=float)
    a = pd.to_numeric(act, errors="coerce").to_numpy(dtype=float)
    cortes = np.unique(np.quantile(r[~np.isnan(r)], np.linspace(0, 1, n_tramos + 1)))
    cortes[0], cortes[-1] = -np.inf, np.inf

    def conteo(v):
        nulos = np.isnan(v)
        return np.r_[np.histogram(v[~nulos], cortes)[0], nulos.sum()].astype(float)

    p, q = _proporciones(conteo(r)), _proporciones(conteo(a))
    return float(((q - p) * np.log(q / p)).sum())


def psi_categorica(ref: pd.Series, act: pd.Series) -> float:
    r, a = ref.astype(str), act.astype(str)
    valores = sorted(set(r) | set(a))
    p = _proporciones(r.value_counts().reindex(valores, fill_value=0).to_numpy(dtype=float))
    q = _proporciones(a.value_counts().reindex(valores, fill_value=0).to_numpy(dtype=float))
    return float(((q - p) * np.log(q / p)).sum())


def psi(variable: str, ref: pd.DataFrame, act: pd.DataFrame) -> float:
    if variable in NUMERICAS:
        return psi_numerica(ref[variable], act[variable])
    return psi_categorica(ref[variable], act[variable])


def prueba_respaldo(variable: str, ref: pd.DataFrame, act: pd.DataFrame) -> tuple[str, float, float]:
    """KS (numéricas) o chi-cuadrado (categóricas): (prueba, estadístico, valor p)."""
    if variable in NUMERICAS:
        r = pd.to_numeric(ref[variable], errors="coerce").dropna()
        a = pd.to_numeric(act[variable], errors="coerce").dropna()
        res = stats.ks_2samp(r, a)
        return "ks", float(res.statistic), float(res.pvalue)
    r, a = ref[variable].astype(str), act[variable].astype(str)
    valores = sorted(set(r) | set(a))
    tabla = np.vstack([r.value_counts().reindex(valores, fill_value=0), a.value_counts().reindex(valores, fill_value=0)])
    tabla = tabla[:, tabla.sum(axis=0) > 0]
    chi2, p, _, _ = stats.chi2_contingency(tabla)
    return "chi2", float(chi2), float(p)


def estado_psi(valor: float) -> str:
    return "alerta" if valor >= PSI_ALERTA else ("aviso" if valor >= PSI_AVISO else "ok")


def referencia_misma_semana(entrenamiento: pd.DataFrame, desde: pd.Timestamp, hasta: pd.Timestamp,
                            columna_ts: str = "trans_ts") -> pd.DataFrame:
    """Filas de entrenamiento de la misma semana del año anterior (364 días antes: mismos días de la semana)."""
    ini = desde.normalize() - pd.Timedelta(days=364)
    fin = hasta.normalize() - pd.Timedelta(days=363)          # exclusivo: incluye todo el último día
    ts = entrenamiento[columna_ts]
    return entrenamiento[(ts >= ini) & (ts < fin)]


def tabla_psi(ref: pd.DataFrame, act: pd.DataFrame, variables=VIGILADAS) -> pd.DataFrame:
    filas = []
    for v in variables:
        valor = psi(v, ref, act)
        prueba, estad, p = prueba_respaldo(v, ref, act)
        filas.append({"variable": v, "psi": valor, "estado": estado_psi(valor), "prueba": prueba,
                      "estadistico": estad, "valor_p": p})
    return pd.DataFrame(filas)
