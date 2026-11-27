"""Ética operativa: desempeño y decisiones por subgrupo, costo de cada error y criterios de retirada.

Datos: las predicciones de la simulación (data/predicciones_completas.parquet, exportado de PRODUCCION.PREDICCIONES
por scripts/exportar_docs.py) con su target ya llegado (lotes 0 a 23), unidas al snapshot de la OBT por trans_num
para el género. El género NO es una entrada del modelo (se excluyó por equidad en el PSet 3); aquí solo se usa para
auditar. La edad sí es una entrada (edad_en_transaccion).

Se reporta para dos ventanas: los lotes SIN alterar (0 a 9), la lectura limpia; y todos los lotes etiquetados
(0 a 23), que incluyen la deriva inducida (D1 cambia la mezcla de categorías y D2 camufla fraudes).

Uso, desde proyecto_final/:  python monitoreo/etica.py
Salidas en docs/etica/: subgrupos.csv, equidad_por_ventana.csv, costo_errores.csv, criterios_retirada.csv, subgrupos.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from datos import cargar_obt  # noqa: E402
from pipeline import COSTO_FALSA_ALARMA, auc_pr  # noqa: E402
from produccion import CATALOGOS, D1_DESDE  # noqa: E402

SALIDA = RAIZ / "docs" / "etica"
EDADES = ([0, 25, 40, 60, 200], ["menos de 25", "25 a 39", "40 a 59", "60 o más"])
RATIO_EQUIDAD = 1.25      # regla de los 4/5 invertida: la tasa de falsas alarmas de un grupo no debe superar 1,25 veces la de otro
# Un lote tiene pocas falsas alarmas por subgrupo (de 0 a ~35): el cociente por lote es ruido. R2 se evalúa en
# ventanas móviles de 4 lotes, con al menos 30 falsas alarmas por grupo y una prueba de dos proporciones.
VENTANA_EQ, MIN_FA, ALFA = 4, 30, 0.05
SOPORTE_FACTOR, SOPORTE_MAX = 5.0, 0.01   # B1: montos > 5 × p95 de su categoría; retirada si superan el 1 % del lote


def cargar() -> pd.DataFrame:
    p = pd.read_parquet(RAIZ / "data" / "predicciones_completas.parquet")
    p = p[p["is_fraud"].notna()].copy()
    e = pd.DataFrame([json.loads(x) for x in p["entradas"]], index=p.index)[["amt", "edad_en_transaccion", "categoria"]]
    p = pd.concat([p.drop(columns=["entradas"]), e], axis=1)
    g = cargar_obt(["trans_num", "gender"])
    p = p.merge(g, on="trans_num", how="left", validate="many_to_one")
    p["is_fraud"] = p["is_fraud"].astype(int)
    p["alerta"] = p["decision"].isin(["verificar", "retener"])
    p["grupo_edad"] = pd.cut(p["edad_en_transaccion"], EDADES[0], labels=EDADES[1], right=False).astype(str)
    p["genero"] = p["gender"].map({"F": "mujer", "M": "hombre"})
    p["ventana"] = np.where(p["lote"] < D1_DESDE, "sin alterar (0-9)", "con deriva (10-23)")
    return p


def metricas(d: pd.DataFrame) -> dict:
    y, a, m = d["is_fraud"].to_numpy(), d["alerta"].to_numpy(), d["amt"].to_numpy(dtype=float)
    leg = y == 0
    n = len(d)
    return {"transacciones": n, "fraudes": int(y.sum()), "prevalencia_pct": 100 * y.mean(),
            "auc_pr": auc_pr(y, d["probabilidad"]) if y.sum() >= 10 and d["probabilidad"].notna().all() else np.nan,
            "recall_pct": 100 * a[y == 1].mean() if y.sum() else np.nan,
            "falsas_alarmas_pct_legitimas": 100 * a[leg].mean(),
            "retenidas_pct_legitimas": 100 * (d["decision"].to_numpy()[leg] == "retener").mean(),
            "tasa_aprobar_pct": 100 * (d["decision"] == "aprobar").mean(),
            "tasa_verificar_pct": 100 * (d["decision"] == "verificar").mean(),
            "tasa_retener_pct": 100 * (d["decision"] == "retener").mean(),
            "fraude_no_detectado_x1000": 1000 * m[(y == 1) & ~a].sum() / n,
            "costo_falsas_alarmas_x1000": 1000 * COSTO_FALSA_ALARMA * (leg & a).sum() / n}


def main() -> dict:
    SALIDA.mkdir(parents=True, exist_ok=True)
    p = cargar()
    filas = []
    for ventana, dv in [("sin alterar (0-9)", p[p["lote"] < D1_DESDE]), ("todos los etiquetados (0-23)", p)]:
        filas.append({"ventana": ventana, "dimension": "total", "grupo": "total", **metricas(dv)})
        for dim in ("genero", "grupo_edad"):
            for g, dg in dv.groupby(dim):
                filas.append({"ventana": ventana, "dimension": dim, "grupo": g, **metricas(dg)})
    S = pd.DataFrame(filas)
    for (v, dim), d in S[S["dimension"] != "total"].groupby(["ventana", "dimension"]):
        S.loc[d.index, "ratio_falsas_alarmas_max_min"] = d["falsas_alarmas_pct_legitimas"].max() / d["falsas_alarmas_pct_legitimas"].min()
    S.round(4).to_csv(SALIDA / "subgrupos.csv", index=False)

    # ---- equidad en ventanas móviles de 4 lotes etiquetados (criterio R2)
    from scipy.stats import norm
    eq = []
    leg = p[p["is_fraud"] == 0]
    for fin in range(VENTANA_EQ - 1, int(p["lote"].max()) + 1):
        w = leg[leg["lote"].between(fin - VENTANA_EQ + 1, fin)]
        for dim in ("genero", "grupo_edad"):
            c = w.groupby(dim)["alerta"].agg(["sum", "count"])
            c = c[c["sum"] >= MIN_FA]
            if len(c) < 2:
                continue
            tasa = c["sum"] / c["count"]
            hi, lo = tasa.idxmax(), tasa.idxmin()
            x1, n1, x2, n2 = c.loc[hi, "sum"], c.loc[hi, "count"], c.loc[lo, "sum"], c.loc[lo, "count"]
            pp = (x1 + x2) / (n1 + n2)
            z = (x1 / n1 - x2 / n2) / np.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
            eq.append({"lotes": f"{fin - VENTANA_EQ + 1}-{fin}", "lote_fin": fin, "dimension": dim, "grupos_evaluados": len(c),
                       "grupo_mas_alto": hi, "fa_mas_alto_pct": 100 * tasa[hi], "grupo_mas_bajo": lo, "fa_mas_bajo_pct": 100 * tasa[lo],
                       "ratio": tasa[hi] / tasa[lo], "valor_p": float(2 * (1 - norm.cdf(abs(z))))})
    E = pd.DataFrame(eq)
    E["sobre_umbral"] = (E["ratio"] > RATIO_EQUIDAD) & (E["valor_p"] < ALFA)
    E.round(5).to_csv(SALIDA / "equidad_por_ventana.csv", index=False)

    # ---- costo de cada tipo de error y quién lo asume
    y, a, dec, m = p["is_fraud"], p["alerta"], p["decision"], p["amt"]
    costos = pd.DataFrame([
        {"error": "falso negativo (fraude aprobado)", "casos": int(((y == 1) & ~a).sum()),
         "costo_usd": float(m[(y == 1) & ~a].sum()), "quien_lo_asume": "el banco (contracargo del monto) y el cliente (gestión de la disputa, tarjeta bloqueada y reemplazada)"},
        {"error": "falso positivo en verificar (legítima con OTP o llamada)", "casos": int(((y == 0) & (dec == "verificar")).sum()),
         "costo_usd": float(COSTO_FALSA_ALARMA * ((y == 0) & (dec == "verificar")).sum()),
         "quien_lo_asume": "el banco (USD 5 por verificación, supuesto del PSet 1) y el cliente legítimo (fricción: un paso más para pagar)"},
        {"error": "falso positivo en retener (legítima retenida para el analista)", "casos": int(((y == 0) & (dec == "retener")).sum()),
         "costo_usd": float(COSTO_FALSA_ALARMA * ((y == 0) & (dec == "retener")).sum()),
         "quien_lo_asume": "el cliente legítimo (compra detenida hasta la revisión; el costo real supera los USD 5 del supuesto) y el banco (tiempo del analista, riesgo de abandono)"},
    ])
    costos.round(2).to_csv(SALIDA / "costo_errores.csv", index=False)

    # ---- criterios de retirada evaluados en la simulación
    mon = pd.read_csv(RAIZ / "docs" / "monitoreo.csv")
    des = mon[mon["grupo"] == "desempeño"].pivot_table(index="lote", columns="metrica", values="valor")
    ratio_negocio = des["perdida_neta"] / des["perdida_reglas"]
    peor_que_reglas = (ratio_negocio > 1).astype(int)
    seguidas_negocio = int((peor_que_reglas.rolling(2).sum() == 2).sum())
    sis = mon[mon["grupo"] == "sistema"].pivot_table(index="lote", columns="metrica", values="valor")
    p95 = CATALOGOS["p95_amt_por_categoria"]
    p["fuera_soporte"] = p["amt"] > SOPORTE_FACTOR * p["categoria"].map(p95).astype(float)
    sop = p.groupby("lote")["fuera_soporte"].mean()
    fs = p[p["fuera_soporte"]]
    criterios = pd.DataFrame([
        {"criterio": "R1 negocio: el modelo pierde más que las reglas fijas",
         "metrica": "pérdida neta del modelo / pérdida de las reglas en el mismo lote etiquetado",
         "umbral": "> 1 en 2 lotes etiquetados seguidos", "respuesta": "interruptor de respaldo (reglas fijas) y reentrenamiento urgente; comité de riesgo",
         "observado": f"máximo {ratio_negocio.max():.3f} (lote {int(ratio_negocio.idxmax())}); lotes > 1: {int(peor_que_reglas.sum())}",
         "se_activo": seguidas_negocio > 0},
        {"criterio": "R2 equidad: falsas alarmas desiguales entre subgrupos",
         "metrica": "tasa de falsas alarmas (legítimas en verificar o retener) del grupo más alto / la del más bajo, por género y por grupo de edad, en ventanas móviles de 4 lotes (grupos con >= 30 falsas alarmas)",
         "umbral": f"> {RATIO_EQUIDAD} (regla de los 4/5) y diferencia significativa (dos proporciones, p < {ALFA})",
         "respuesta": "revisión de equidad por el comité de riesgo: análisis de causa (variables que actúan como proxy), ajuste de umbral o reentrenamiento con restricción de equidad; si no se corrige en el siguiente ciclo, retirar el modelo (respaldo general, nunca un trato distinto por grupo)",
         "observado": "; ".join(f"{dim}: {int(d['sobre_umbral'].sum())} de {len(d)} ventanas sobre el umbral (cociente máximo {d['ratio'].max():.2f}, {d.loc[d['ratio'].idxmax(), 'grupo_mas_alto']} frente a {d.loc[d['ratio'].idxmax(), 'grupo_mas_bajo']}, lotes {d.loc[d['ratio'].idxmax(), 'lotes']})" for dim, d in E.groupby("dimension")),
         "se_activo": bool(E["sobre_umbral"].any())},
        {"criterio": "R3 montos fuera de soporte (hallazgo B1)",
         "metrica": f"% de transacciones del lote con monto > {SOPORTE_FACTOR:g} × p95 de su categoría (zona donde el modelo baja la probabilidad, prueba B1 en xfail)",
         "umbral": f"> {100 * SOPORTE_MAX:g} % del lote; y cualquier transacción en esa zona", "respuesta": "regla de protección: esas transacciones van como mínimo a verificar; si superan el 1 % del lote, retirar el modelo (respaldo) hasta reentrenar con datos de esos montos",
         "observado": f"máximo {100 * sop.max():.3f} % del lote (lote {int(sop.idxmax())}); {len(fs)} transacciones en la zona ({int(fs['is_fraud'].sum())} fraudes), {int((fs['decision'] == 'aprobar').sum())} aprobadas por el modelo",
         "se_activo": bool((sop > SOPORTE_MAX).any())},
        {"criterio": "R4 sistema: el servicio no responde a tiempo",
         "metrica": "latencia p95 de POST /predecir y tasa de 5xx por lote",
         "umbral": "p95 > 200 ms o 5xx > 1 % en el lote", "respuesta": "interruptor de respaldo automático (reglas fijas) hasta restablecer el servicio; aviso a plataforma",
         "observado": f"p95 máximo {sis['latencia_online_p95_ms'].max():.1f} ms; 5xx totales {int(sis['errores_5xx'].sum())}",
         "se_activo": bool((sis["latencia_online_p95_ms"] > 200).any() or (sis["errores_5xx"] / sis["solicitudes"] > 0.01).any())},
    ])
    criterios.to_csv(SALIDA / "criterios_retirada.csv", index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ejes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    v = S[(S["ventana"] == "sin alterar (0-9)") & (S["dimension"] != "total")]
    tot = S[(S["ventana"] == "sin alterar (0-9)") & (S["dimension"] == "total")].iloc[0]
    for ax, col, titulo in [(ejes[0], "falsas_alarmas_pct_legitimas", "Falsas alarmas (% de legítimas)"),
                            (ejes[1], "recall_pct", "Fraudes detectados (% de fraudes)")]:
        ax.barh(v["grupo"], v[col], color="#257de0", height=0.6)
        ax.axvline(tot[col], color="#191919", ls="--", lw=1, label=f"total {tot[col]:.2f}")
        for yy, xx in zip(v["grupo"], v[col]):
            ax.text(xx, yy, f" {xx:.2f}", va="center", fontsize=8, color="#191919")
        ax.set_title(titulo, fontsize=10); ax.legend(fontsize=8, loc="lower right")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Desempeño por subgrupo · lotes sin alterar (0-9), champion v1", fontsize=11)
    fig.tight_layout(); fig.savefig(SALIDA / "subgrupos.png", dpi=120); plt.close(fig)
    return {"subgrupos": S, "equidad": E, "costos": costos, "criterios": criterios}


if __name__ == "__main__":
    r = main()
    pd.set_option("display.width", 220)
    print(r["subgrupos"][["ventana", "dimension", "grupo", "transacciones", "fraudes", "auc_pr", "recall_pct",
                          "falsas_alarmas_pct_legitimas", "retenidas_pct_legitimas", "tasa_aprobar_pct",
                          "ratio_falsas_alarmas_max_min"]].round(3).to_string(index=False))
    print(r["costos"][["error", "casos", "costo_usd"]].round(0).to_string(index=False))
    for _, c in r["criterios"].iterrows():
        print(f"- {c['criterio']}: {c['observado']} -> activado: {c['se_activo']}")
