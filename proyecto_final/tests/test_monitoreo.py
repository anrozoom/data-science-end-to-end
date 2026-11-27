"""Pruebas del monitoreo (monitoreo/deriva.py y monitoreo/alertas.py) con datos sintéticos fijos."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "monitoreo"))

import alertas  # noqa: E402
from deriva import PSI_ALERTA, PSI_AVISO, estado_psi, psi_categorica, psi_numerica, referencia_misma_semana  # noqa: E402

U = json.loads((RAIZ / "docs" / "monitoreo" / "umbrales.json").read_text(encoding="utf-8"))
rng = np.random.default_rng(0)


def test_psi_misma_distribucion_es_casi_cero():
    a, b = pd.Series(rng.normal(size=20_000)), pd.Series(rng.normal(size=20_000))
    assert psi_numerica(a, b) < 0.01


def test_psi_detecta_desplazamiento_importante():
    a, b = pd.Series(rng.normal(size=20_000)), pd.Series(rng.normal(1.0, 1, size=20_000))
    assert psi_numerica(a, b) >= PSI_ALERTA


def test_psi_categorica_y_categoria_nueva():
    ref = pd.Series(["a"] * 500 + ["b"] * 500)
    assert psi_categorica(ref, ref.copy()) == 0
    assert psi_categorica(ref, pd.Series(["a"] * 900 + ["c"] * 100)) >= PSI_ALERTA


def test_psi_cuenta_los_nulos_como_tramo():
    ref = pd.Series(rng.normal(size=10_000))
    con_nulos = ref.copy()
    con_nulos[: 3000] = np.nan
    assert psi_numerica(ref, con_nulos) >= PSI_AVISO


def test_estados_de_psi():
    assert (estado_psi(0.05), estado_psi(0.10), estado_psi(0.25)) == ("ok", "aviso", "alerta")


def test_referencia_misma_semana_conserva_los_dias_de_la_semana():
    ent = pd.DataFrame({"trans_ts": pd.date_range("2019-06-01", "2019-12-31 23:00", freq="h")})
    ref = referencia_misma_semana(ent, pd.Timestamp("2020-07-01 00:10"), pd.Timestamp("2020-07-07 23:50"))
    assert ref["trans_ts"].dt.normalize().nunique() == 7
    assert set(ref["trans_ts"].dt.dayofweek) == set(range(7))
    assert ref["trans_ts"].min().dayofweek == pd.Timestamp("2020-07-01").dayofweek


def _metricas(**cambios):
    m = {"sistema": {"solicitudes": 210, "errores_4xx": 0, "errores_5xx": 0, "latencia_online_p95_ms": 20.0,
                     "volumen": 20000, "volumen_2019": 19900, "volumen_relativo_2019": 1.005},
         "datos": {"fuera_de_soporte_pct": {"amt": 0.0}, "categorias_no_vistas": 0, "nulos_pct": {"amt": 0.0},
                   "psi": [{"variable": "amt", "psi": 0.01, "estado": "ok", "prueba": "ks", "valor_p": 0.5}]},
         "modelo": {"tasa_alertas": U["tasa_alertas"]["media"]},
         "etiquetado": {"lote": 3, "auc_pr": 0.96, "version": "1", "perdida_neta": 300.0, "perdida_reglas": 5000.0},
         "disparo": {"motivo": "ninguno", "lotes": [], "auc_lotes": [], "version": "1"}}
    for k, v in cambios.items():
        m[k] = {**m[k], **v}
    return m


def test_un_lote_normal_no_dispara_alertas():
    assert alertas.evaluar(_metricas(), U) == []


def test_caida_de_desempeno_y_disparo_critico():
    m = _metricas(etiquetado={"auc_pr": 0.60},
                  disparo={"motivo": "desempeño", "lotes": [2, 3], "auc_lotes": [0.7, 0.6], "version": "1"})
    ids = {a["id_alerta"]: a["severidad"] for a in alertas.evaluar(m, U)}
    assert ids == {"MOD-DES-1": "alta", "MOD-DES-2": "crítica"}


def test_deriva_de_datos_sola_no_es_critica():
    m = _metricas(datos={"psi": [{"variable": "categoria", "psi": 0.30, "estado": "alerta", "prueba": "chi2", "valor_p": 0.0}]},
                  sistema={"volumen_relativo_2019": 0.44})
    sev = {a["id_alerta"]: a["severidad"] for a in alertas.evaluar(m, U)}
    assert sev == {"DAT-PSI": "media", "SIS-VOL": "media"}


def test_la_plantilla_tiene_todos_los_campos():
    assert list(alertas.PLANTILLA.columns) == ["id", "metrica", "umbral", "ventana", "severidad", "receptor", "accion"]
    assert alertas.PLANTILLA["severidad"].isin(alertas.SEVERIDADES).all()
    assert alertas.PLANTILLA["id"].is_unique
