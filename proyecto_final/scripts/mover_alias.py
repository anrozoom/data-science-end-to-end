"""Mueve un alias de centinela-modelo (rollback o restauración) y espera a que la API lo sirva SOLA.

No llama a POST /recargar: la API vuelve a resolver el alias cada RECARGA_SEGUNDOS (30 s), así se ve que
cambiar de versión no requiere reconstruir la imagen ni reiniciar el contenedor. Deja la evidencia en
docs/demos/rollback.csv y una etiqueta en la versión de MLflow.

Uso, desde proyecto_final/:  python scripts/mover_alias.py <version> [--motivo rollback] [--alias champion]
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from produccion import NOMBRE_MODELO, configurar_mlflow  # noqa: E402

API = "http://localhost:8000"


def main(version: str, motivo: str, alias: str) -> None:
    configurar_mlflow()
    from mlflow import MlflowClient
    c = MlflowClient()
    antes = c.get_model_version_by_alias(NOMBRE_MODELO, alias).version
    api_antes = requests.get(f"{API}/modelo", timeout=10).json()
    print(f"Antes:   alias {alias} -> v{antes}; la API sirve la v{api_antes['version']} (run {api_antes['run_id'][:8]})")
    t0 = time.time()
    c.set_registered_model_alias(NOMBRE_MODELO, alias, version)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    c.set_model_version_tag(NOMBRE_MODELO, version, f"{motivo}_utc", ts)
    print(f"{ts} UTC: alias {alias} -> v{version} en MLflow (sin tocar la imagen ni el contenedor de la API)")
    while True:
        m = requests.get(f"{API}/modelo", timeout=10).json()
        if str(m["version"]) == str(version):
            break
        if time.time() - t0 > 120:
            sys.exit(f"La API sigue en la v{m['version']} después de 120 s")
        time.sleep(2)
    seg = time.time() - t0
    print(f"Después: GET /modelo -> v{m['version']} (run {m['run_id'][:8]}, umbrales {m['umbral_verificar']:.4f} / "
          f"{m['umbral_retener']:.4f}) a los {seg:.0f} s, por la recarga periódica de la API")
    archivo = RAIZ / "docs" / "demos" / "rollback.csv"
    nuevo = not archivo.exists()
    with archivo.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["ts_utc", "motivo", "alias", "version_antes", "version_despues", "api_version_despues",
                        "run_id_despues", "segundos_hasta_servir"])
        w.writerow([ts, motivo, alias, antes, version, m["version"], m["run_id"], round(seg, 1)])


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("version")
    a.add_argument("--motivo", default="rollback")
    a.add_argument("--alias", default="champion")
    x = a.parse_args()
    main(x.version, x.motivo, x.alias)
