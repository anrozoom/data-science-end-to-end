"""Resumen de la simulación vigente, leído de CENTINELA.PRODUCCION (sin recalcular nada).

Escribe en docs/simulacion/:
  alertas_por_paso.csv           alertas por paso y lote, con su severidad, y si el lote estaba alterado
  reentrenamientos_simulacion.csv  cada reentrenamiento con su recomendación y la decisión humana
  negocio_por_lote.csv           por lote etiquetado: pérdida del modelo, de las reglas fijas y de no hacer nada
                                 (USD y por 1.000 transacciones), AUC-PR, prevalencia y versión que lo sirvió
Uso, desde proyecto_final/:  python simulacion/resumen_simulacion.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from produccion import D1_DESDE, D2_DESDE, INICIO_SIM_SQL, Snowflake  # noqa: E402

SALIDA = RAIZ / "docs" / "simulacion"


def main() -> None:
    sf = Snowflake()
    al = sf.sql(f"""SELECT PASO, LOTE, ID_ALERTA, SEVERIDAD, VARIABLE, VALOR, UMBRAL, RECEPTOR, MENSAJE
                    FROM PRODUCCION.ALERTAS WHERE INICIO_SIMULACION = {INICIO_SIM_SQL} ORDER BY PASO, ID_ALERTA""")
    al["lote_alterado"] = al["lote"] >= D1_DESDE
    re = sf.sql(f"""SELECT PASO, MOTIVO, LOTE_EVALUACION, VENTANA_HASTA_LOTE, CHAMPION_VERSION, CHALLENGER_VERSION, RUN_ID,
                    AUC_PR_CHAMPION, AUC_PR_CHALLENGER, PERDIDA_X1000_CHAMPION, PERDIDA_X1000_CHALLENGER, MEJORA_X1000,
                    UMBRAL_MEJORA_X1000, RECOMENDACION, DECISION, MOTIVO_DECISION, TS_DECISION
                    FROM PRODUCCION.REENTRENAMIENTOS WHERE INICIO_SIMULACION = {INICIO_SIM_SQL} ORDER BY PASO""")
    de = sf.sql(f"""SELECT PASO, LOTE, METRICA, VALOR, MODELO_VERSION FROM PRODUCCION.MONITOREO
                    WHERE INICIO_SIMULACION = {INICIO_SIM_SQL} AND GRUPO = 'desempeño'""")
    sf.cerrar()
    n = de.pivot_table(index=["lote", "paso", "modelo_version"], columns="metrica", values="valor").reset_index()
    for c in ("perdida_neta", "perdida_reglas", "perdida_sin_modelo"):
        n[c.replace("perdida_neta", "perdida_modelo") + "_x1000"] = 1000 * n[c] / n["filas"]
    n = n.rename(columns={"paso": "paso_llegada_target", "modelo_version": "version"})
    n["deriva"] = n["lote"].map(lambda k: "D1+D2" if k >= D2_DESDE else ("D1" if k >= D1_DESDE else "sin alterar"))
    cols = ["lote", "paso_llegada_target", "version", "deriva", "filas", "fraudes", "prevalencia", "auc_pr", "recall",
            "perdida_neta", "perdida_reglas", "perdida_sin_modelo", "perdida_modelo_x1000", "perdida_reglas_x1000",
            "perdida_sin_modelo_x1000"]
    n = n[cols].sort_values("lote")
    SALIDA.mkdir(parents=True, exist_ok=True)
    al.to_csv(SALIDA / "alertas_por_paso.csv", index=False)
    re.to_csv(SALIDA / "reentrenamientos_simulacion.csv", index=False)
    n.round(4).to_csv(SALIDA / "negocio_por_lote.csv", index=False)

    print("ALERTAS (severidad media o mayor) por paso:")
    g = al[al["severidad"] != "baja"].groupby(["paso", "lote"])["id_alerta"].apply(lambda s: ", ".join(sorted(s)))
    print(g.to_string())
    bajas = al[al["severidad"] == "baja"].groupby("paso")["id_alerta"].count()
    print("\nAvisos informativos (baja) por paso:", bajas.to_dict())
    sin_alt = al[(al["lote"] < D1_DESDE) & (al["severidad"] != "baja")]
    print(f"\nAlertas de severidad media o mayor en lotes SIN alterar (0..{D1_DESDE - 1}): {len(sin_alt)}")
    print(sin_alt[["paso", "lote", "id_alerta", "valor"]].to_string(index=False) if len(sin_alt) else "  ninguna")
    print("\nREENTRENAMIENTOS:")
    print(re[["paso", "motivo", "lote_evaluacion", "champion_version", "challenger_version", "perdida_x1000_champion",
              "perdida_x1000_challenger", "mejora_x1000", "recomendacion", "decision"]].round(2).to_string(index=False))
    print("\nNEGOCIO por lote etiquetado (por 1.000 transacciones):")
    print(n[["lote", "version", "deriva", "prevalencia", "auc_pr", "perdida_modelo_x1000", "perdida_reglas_x1000",
             "perdida_sin_modelo_x1000"]].round(3).to_string(index=False))
    t = n[["perdida_neta", "perdida_reglas", "perdida_sin_modelo", "filas"]].sum()
    print(f"\nTOTAL lotes 0..{int(n['lote'].max())}: modelo {t.perdida_neta:,.0f} USD | reglas {t.perdida_reglas:,.0f} USD | "
          f"sin modelo {t.perdida_sin_modelo:,.0f} USD ({int(t.filas):,} transacciones)")


if __name__ == "__main__":
    main()
