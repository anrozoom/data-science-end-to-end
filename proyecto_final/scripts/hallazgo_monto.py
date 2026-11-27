"""Hallazgo: el champion baja la probabilidad cuando el monto queda muy por encima del p95 de su categoría.

Sobre la muestra fija de prueba (tests/fixtures), lleva el monto de cada transacción a k × p95 de su
categoría (mismo historial: monto_relativo se recalcula) y mide la probabilidad media del modelo para
fraudes y legítimas. También cuenta, en ENTRENAMIENTO, cuántos fraudes hay por encima de cada múltiplo.
Salida: docs/hallazgos/monto_vs_p95.csv, monto_vs_p95.png y soporte_entrenamiento.csv.
Uso, desde proyecto_final/:  python scripts/hallazgo_monto.py
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
RAIZ = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(RAIZ / "src"))
import mlflow
from datos import cargar_obt
from pipeline import dividir
DOC = RAIZ / "docs" / "hallazgos"; DOC.mkdir(parents=True, exist_ok=True)
cat = json.loads((RAIZ / "api" / "catalogos.json").read_text())
m = mlflow.sklearn.load_model(str(RAIZ / "tests" / "fixtures" / "modelo_champion"))
mu = pd.read_parquet(RAIZ / "tests" / "fixtures" / "muestra_prueba.parquet")
X = mu.drop(columns=["trans_num", "is_fraud", "probabilidad_esperada"]); fr = mu["is_fraud"].to_numpy() == 1
p95 = X["categoria"].map(cat["p95_amt_por_categoria"]).astype(float)
filas = []
for k in [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10]:
    Y = X.copy(); Y["amt"] = k * p95; Y["monto_relativo"] = Y["amt"] / X["monto_medio_previo"]
    p = m.predict_proba(Y)[:, 1]
    filas.append({"multiplo_p95": k, "prob_media_fraudes": float(p[fr].mean()), "prob_media_legitimas": float(p[~fr].mean()),
                  "pct_fraudes_retener_u2": float((p[fr] >= 0.8493347639207266).mean() * 100)})
curva = pd.DataFrame(filas); curva.to_csv(DOC / "monto_vs_p95.csv", index=False)
Xe, ye, _, _, ent, _ = dividir(cargar_obt())
r = Xe["amt"] / Xe["categoria"].map(cat["p95_amt_por_categoria"]).astype(float)
sop = pd.DataFrame([{"monto_mayor_a": f"{k}x p95", "transacciones": int((r > k).sum()), "fraudes": int(ye[r > k].sum())} for k in (1, 2, 3, 5, 10)])
sop.loc[len(sop)] = {"monto_mayor_a": "fraude más caro (USD)", "transacciones": None, "fraudes": float(Xe["amt"][ye == 1].max())}
sop.to_csv(DOC / "soporte_entrenamiento.csv", index=False)
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(curva["multiplo_p95"], curva["prob_media_fraudes"], "o-", color="#ef4444", label="fraudes (muestra de prueba)")
ax.plot(curva["multiplo_p95"], curva["prob_media_legitimas"], "o-", color="#3b82f6", label="legítimas")
ax.axhline(0.8493, color="#ef4444", ls=":", lw=1, label="umbral retener 0,85"); ax.axhline(0.24, color="#f59e0b", ls=":", lw=1, label="umbral verificar 0,24")
ax.set_xscale("log"); ax.set_xlabel("monto como múltiplo del p95 de su categoría (log)"); ax.set_ylabel("probabilidad media del modelo")
ax.set_title("El riesgo sube con el monto hasta ~2×p95 y luego cae: no hay fraudes así de caros en Sparkov", fontsize=9)
ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(DOC / "monto_vs_p95.png", dpi=120)
print(curva.round(4).to_string(index=False)); print(sop.to_string(index=False))
