"""Exporta el fixture de pruebas para CI (sin acceso al servidor de MLflow):

tests/fixtures/modelo_champion/   el champion exportado con mlflow.sklearn.save_model (incluye pipeline.py)
tests/fixtures/info_modelo.json   versión, run_id y umbrales (los lee la API cuando MODELO_URI es una ruta)
tests/fixtures/muestra_prueba.parquet   muestra FIJA de la partición de prueba: todos los fraudes + 8.000
                                        legítimas (semilla 42), con el target y la probabilidad esperada
tests/fixtures/metricas_esperadas.json  AUC-PR esperada en la muestra (también se registra en la corrida
                                        del champion en MLflow como métrica ci_muestra_auc_pr)

Uso, desde proyecto_final/ (con MLflow levantado):  python scripts/exportar_fixture.py
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
import mlflow  # noqa: E402
from mlflow import MlflowClient  # noqa: E402
from sklearn.metrics import average_precision_score  # noqa: E402

from datos import cargar_obt, metadatos_snapshot  # noqa: E402
from pipeline import dividir  # noqa: E402

FIX = RAIZ / "tests" / "fixtures"
SEMILLA, N_LEGITIMAS = 42, 8000

env = (RAIZ / ".env").read_text().splitlines()
mlflow.set_tracking_uri(next((l.split("=", 1)[1] for l in env if l.startswith("MLFLOW_TRACKING_URI=")), "http://127.0.0.1:5055"))
c = MlflowClient()
v = c.get_model_version_by_alias("centinela-modelo", "champion")
modelo = mlflow.sklearn.load_model(f"models:/centinela-modelo/{v.version}")
info = mlflow.models.get_model_info(f"models:/centinela-modelo/{v.version}")

_, _, Xp, yp, _, pru = dividir(cargar_obt())
rng = np.random.default_rng(SEMILLA)
idx = np.sort(np.concatenate([np.where(yp.values == 1)[0],
                              rng.choice(np.where(yp.values == 0)[0], N_LEGITIMAS, replace=False)]))
muestra = Xp.iloc[idx].reset_index(drop=True)
muestra.insert(0, "trans_num", pru["trans_num"].iloc[idx].to_numpy())
muestra["is_fraud"] = yp.values[idx]
muestra["probabilidad_esperada"] = modelo.predict_proba(Xp.iloc[idx])[:, 1]
auc = float(average_precision_score(muestra["is_fraud"], muestra["probabilidad_esperada"]))

shutil.rmtree(FIX / "modelo_champion", ignore_errors=True)
FIX.mkdir(parents=True, exist_ok=True)
mlflow.sklearn.save_model(modelo, FIX / "modelo_champion", signature=info.signature,
                          input_example=Xp.iloc[idx[:5]], code_paths=[str(RAIZ / "src" / "pipeline.py")])
muestra.to_parquet(FIX / "muestra_prueba.parquet", index=False)
meta = {"nombre": "centinela-modelo", "alias": "champion (copia para CI)", "version": v.version, "run_id": v.run_id,
        "umbral_verificar": float(v.tags["umbral_decision"]), "umbral_retener": float(v.tags["umbral_retener"])}
(FIX / "modelo_champion" / "info_modelo.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
(FIX / "info_modelo.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
esperadas = {"muestra": f"todos los fraudes de la prueba + {N_LEGITIMAS} legítimas (semilla {SEMILLA})",
             "filas": int(len(muestra)), "fraudes": int(muestra["is_fraud"].sum()),
             "auc_pr_muestra": auc, "metrica_mlflow": "ci_muestra_auc_pr", "run_id": v.run_id, "version": v.version,
             "datos_sha256": metadatos_snapshot()["sha256"],
             "prueba_completa_auc_pr_registrada": c.get_run(v.run_id).data.metrics.get("prueba_auc_pr_prueba")}
(FIX / "metricas_esperadas.json").write_text(json.dumps(esperadas, indent=2), encoding="utf-8")
c.log_metric(v.run_id, "ci_muestra_auc_pr", auc)
print(json.dumps(esperadas, indent=2))
