"""Genera api/catalogos.json: categorías permitidas y p95 del monto por categoría, SOLO con entrenamiento.

- Las categorías (categoria, canal, state) son las vistas en entrenamiento: la API rechaza otras (422).
- El p95 por categoría es lo único que aprende la regla fija del PSet 1, que la API usa como respaldo.
Uso, desde proyecto_final/:  python scripts/catalogos_api.py
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from datos import cargar_obt, metadatos_snapshot  # noqa: E402
from pipeline import dividir  # noqa: E402

X, *_ = dividir(cargar_obt())
cat = {
    "fuente": "partición de entrenamiento (ene-2019 a jun-2020) del snapshot de la OBT",
    "datos_sha256": metadatos_snapshot()["sha256"],
    "categoria": sorted(X["categoria"].unique().tolist()),
    "canal": sorted(X["canal"].unique().tolist()),
    "state": sorted(X["state"].unique().tolist()),
    "p95_amt_por_categoria": {k: round(float(v), 4) for k, v in X.groupby("categoria")["amt"].quantile(0.95).items()},
    "regla_monto_minimo_nocturno": 100.0,
    "regla_distancia_km": 100.0,
}
(RAIZ / "api" / "catalogos.json").write_text(json.dumps(cat, indent=2, ensure_ascii=False), encoding="utf-8")
print({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in cat.items()})
