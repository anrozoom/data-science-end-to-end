"""Genera notebooks/06_simulacion_produccion.ipynb y notebooks/07_analisis_monitoreo.ipynb (sin salida).
Se ejecutan con Restart + Run All (equivalente):
    jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=900 notebooks/06_simulacion_produccion.ipynb
Ninguno de los dos cambia el estado de Snowflake ni de MLflow: solo leen y guardan gráficos en docs/.
"""
from pathlib import Path

import nbformat as nbf

RAIZ = Path(__file__).resolve().parents[1]
COMUN = '''import sys, json, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
RAIZ = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ / "monitoreo")]
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import display, Image
pd.set_option("display.max_columns", 40); pd.set_option("display.width", 200)
# Paleta (skill de visualización): categórica en orden fijo; estados reservados para severidad.
MODELO, REGLAS, SIN_MODELO, GRIS = "#257de0", "#f47230", "#00b894", "#666666"
SEV = {"crítica": "#dc3c3d", "alta": "#f18a59", "media": "#fbb315", "baja": "#9c9c9c"}
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": .25,
                     "figure.dpi": 110, "font.size": 9})
D1, D2 = 10, 14
def franjas(ax):
    ax.axvspan(D1 - .5, D2 - .5, color=GRIS, alpha=.07, lw=0); ax.axvspan(D2 - .5, 25.5, color=GRIS, alpha=.14, lw=0)
    y = ax.get_ylim()[1]
    ax.text(D1 - .3, y, "D1", va="top", fontsize=8, color=GRIS); ax.text(D2 - .3, y, "D1+D2", va="top", fontsize=8, color=GRIS)
'''


def nb(celdas):
    n = nbf.v4.new_notebook()
    n.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    n.cells = [nbf.v4.new_markdown_cell(c[3:]) if c.startswith("md:") else nbf.v4.new_code_cell(c) for c in celdas]
    return n


N06 = [
    "md:# 06 · Simulación de producción\n\nProyecto Centinela (PSet 4). Cómo se construyeron los 26 lotes semanales de la "
    "partición de prueba, qué alteró la deriva inducida, cómo pasó el tráfico por la API y la trazabilidad de una "
    "predicción hasta el snapshot. **Solo lee** Snowflake (`CENTINELA.PRODUCCION`), MLflow y `docs/`; no cambia nada. "
    "Diseño: `docs/simulacion/diseno_deriva.md`.",
    COMUN + '''from produccion import Snowflake, INICIO_SIM_SQL, FILTRO_SIM, N_LOTES, configurar_mlflow
sf = Snowflake()
print("Simulación vigente desde", sf.sql(f"SELECT {INICIO_SIM_SQL} AS i")["i"].iloc[0], "UTC")''',
    "md:## 1. Lotes y prevalencia\n\nD1 quita el 70 % de las legítimas presenciales y conserva todos los fraudes: "
    "la prevalencia sube desde el lote 10 (por eso la AUC-PR de los lotes 10 a 13 no cae, o incluso sube).",
    '''lotes = sf.sql("SELECT * FROM PRODUCCION.LOTES_RESUMEN ORDER BY LOTE")
display(lotes[["lote", "desde", "hasta", "filas_originales", "fraudes", "prevalencia_original_pct", "d1_legitimas_quitadas",
               "d2_fraudes_camuflados", "filas", "prevalencia_pct", "paso_llegada_target"]].round(3))
fig, ax = plt.subplots(1, 2, figsize=(11, 3.4))
ax[0].bar(lotes["lote"], lotes["filas_originales"], color="#cce3fd", label="originales")
ax[0].bar(lotes["lote"], lotes["filas"], color=MODELO, label="servidas a la API")
ax[0].set_title("Transacciones por lote"); ax[0].legend(fontsize=8); franjas(ax[0])
ax[1].plot(lotes["lote"], lotes["prevalencia_original_pct"], "o-", color=GRIS, label="original")
ax[1].plot(lotes["lote"], lotes["prevalencia_pct"], "o-", color=MODELO, label="servida (con D1)")
ax[1].set_title("Prevalencia de fraude (%)"); ax[1].legend(fontsize=8); franjas(ax[1])
for a in ax: a.set_xlabel("lote (semana)")
fig.tight_layout(); fig.savefig(RAIZ / "docs/simulacion/lotes_prevalencia.png", dpi=120); plt.show()''',
    "md:## 2. Deriva conceptual D2: fraudes camuflados\n\nDesde el lote 14, la mitad de los fraudes toma un monto legítimo "
    "típico de su categoría y una hora diurna. Se comparan los valores originales con los servidos.",
    '''d2 = sf.sql("SELECT LOTE, AMT, AMT_ORIGINAL, HORA, HORA_ORIGINAL FROM PRODUCCION.LOTES WHERE ALTERADA_D2 AND LOTE < 26")
print(f"{len(d2)} fraudes camuflados en los lotes {d2.lote.min()} a {d2.lote.max()}")
print("monto: mediana original", round(d2.amt_original.median(), 2), "-> servida", round(d2.amt.median(), 2))
print("% nocturnos (22-04): original", round(100 * d2.hora_original.isin([22, 23, 0, 1, 2, 3]).mean(), 1), "-> servido", round(100 * d2.hora.isin([22, 23, 0, 1, 2, 3]).mean(), 1))
fig, ax = plt.subplots(1, 2, figsize=(11, 3.4))
b = np.linspace(0, 1400, 36)
ax[0].hist(d2.amt_original.clip(upper=1400), b, color=GRIS, alpha=.6, label="original"); ax[0].hist(d2.amt.clip(upper=1400), b, color=MODELO, alpha=.7, label="servido")
ax[0].set_title("Monto de los fraudes camuflados (USD)"); ax[0].legend(fontsize=8)
h = np.arange(25) - .5
ax[1].hist(d2.hora_original, h, color=GRIS, alpha=.6, label="original"); ax[1].hist(d2.hora, h, color=MODELO, alpha=.7, label="servida")
ax[1].set_title("Hora de los fraudes camuflados"); ax[1].legend(fontsize=8)
fig.tight_layout(); fig.savefig(RAIZ / "docs/simulacion/deriva_d2_montos_horas.png", dpi=120); plt.show()''',
    "md:## 3. Tráfico por la API\n\n200 transacciones por lote van una por una a `POST /predecir` (latencia online) y el "
    "resto, en bloques, a `POST /predecir_lote`. Cada una queda registrada en `PRODUCCION.PREDICCIONES`.",
    '''mon = pd.read_csv(RAIZ / "docs/monitoreo.csv")
sis = mon[mon.grupo == "sistema"].pivot_table(index="lote", columns="metrica", values="valor")
mod = mon[mon.grupo == "modelo"].pivot_table(index="lote", columns="metrica", values="valor")
reg = sf.sql(f"SELECT COUNT(*) AS n, COUNT(DISTINCT TRANS_NUM) AS d FROM PRODUCCION.PREDICCIONES WHERE {FILTRO_SIM} AND LOTE < {N_LOTES}")
print("predicciones registradas:", int(reg.n[0]), "| transacciones distintas:", int(reg.d[0]), "| filas en LOTES:", int(lotes.filas.sum()))
print("latencia online p50: mediana por lote", round(sis.latencia_online_p50_ms.median(), 1), "ms | p95 máximo", round(sis.latencia_online_p95_ms.max(), 1), "ms | 4xx", int(sis.errores_4xx.sum()), "| 5xx", int(sis.errores_5xx.sum()))
fig, ax = plt.subplots(1, 2, figsize=(11, 3.4))
ax[0].plot(sis.index, sis.latencia_online_p50_ms, "o-", color=MODELO, label="p50"); ax[0].plot(sis.index, sis.latencia_online_p95_ms, "o-", color=REGLAS, label="p95")
ax[0].set_title("Latencia de POST /predecir (ms)"); ax[0].legend(fontsize=8); franjas(ax[0])
ax[1].plot(mod.index, 100 * mod.tasa_verificar, "o-", color=REGLAS, label="verificar"); ax[1].plot(mod.index, 100 * mod.tasa_retener, "o-", color=MODELO, label="retener")
ax[1].set_title("Decisiones por lote (% de transacciones)"); ax[1].legend(fontsize=8); franjas(ax[1])
for a in ax: a.set_xlabel("lote (semana)")
fig.tight_layout(); fig.savefig(RAIZ / "docs/simulacion/trafico_api.png", dpi=120); plt.show()''',
    "md:## 4. Trazabilidad de una predicción\n\nDe una predicción de la simulación a la versión del modelo, su corrida en "
    "MLflow y el snapshot de datos con el que se entrenó.",
    '''import mlflow
from mlflow import MlflowClient
configurar_mlflow(); c = MlflowClient()
p = sf.sql(f"""SELECT p.ID_PREDICCION, p.TS_UTC, p.TRANS_NUM, p.LOTE, p.PROBABILIDAD, p.DECISION, p.MODELO_VERSION, p.RUN_ID,
                     t.IS_FRAUD, l.DATOS_SHA256 FROM PRODUCCION.PREDICCIONES p
              JOIN PRODUCCION.TARGETS_LLEGADOS t ON t.TRANS_NUM = p.TRANS_NUM AND t.LOTE = p.LOTE
              JOIN PRODUCCION.LOTES l ON l.TRANS_NUM = p.TRANS_NUM AND l.LOTE = p.LOTE
              WHERE p.{FILTRO_SIM.replace("TS_UTC", "p.TS_UTC")} AND p.LOTE = 22 AND t.IS_FRAUD = 1 AND p.DECISION = 'retener'
              ORDER BY p.TS_UTC LIMIT 1""").iloc[0]
run = c.get_run(p.run_id)
v = c.get_model_version("centinela-modelo", p.modelo_version)
traza = {"prediccion": p.id_prediccion, "trans_num": p.trans_num, "lote": int(p.lote), "probabilidad": round(float(p.probabilidad), 4),
         "decision": p.decision, "fraude_confirmado": int(p.is_fraud), "version": p.modelo_version, "run_id": p.run_id,
         "fase_de_la_corrida": run.data.tags.get("fase"), "motivo": run.data.tags.get("motivo"), "ventana": run.data.params.get("ventana"),
         "snapshot_sha256_de_la_corrida": run.data.params.get("datos_sha256"), "snapshot_sha256_del_lote": p.datos_sha256,
         "decision_de_promocion": v.tags.get("decision")}
print(json.dumps(traza, indent=2, ensure_ascii=False))
assert traza["snapshot_sha256_de_la_corrida"] == traza["snapshot_sha256_del_lote"]''',
    "md:**Conclusión.** Los 26 lotes pasaron completos por la API: hay una predicción registrada por cada transacción "
    "servida, y cada una se puede seguir hasta la versión, la corrida y el snapshot. Las cifras de latencia y "
    "decisiones de este notebook alimentan el monitoreo (`07_analisis_monitoreo.ipynb`).",
    "sf.cerrar()",
]

N07 = [
    "md:# 07 · Análisis del monitoreo\n\nProyecto Centinela (PSet 4). Umbrales, deriva, desempeño, alertas, "
    "reentrenamientos, resultado de negocio y ética de la simulación de producción. Lee `docs/` (exportes de "
    "`CENTINELA.PRODUCCION`) y vuelve a calcular la ética con `monitoreo/etica.py`. No cambia nada en Snowflake ni en MLflow.",
    COMUN + '''D = RAIZ / "docs"
mon = pd.read_csv(D / "monitoreo.csv"); al = pd.read_csv(D / "alertas.csv")
re = pd.read_csv(D / "simulacion/reentrenamientos_simulacion.csv"); U = json.loads((D / "monitoreo/umbrales.json").read_text())
des = mon[mon.grupo == "desempeño"].pivot_table(index=["lote", "modelo_version"], columns="metrica", values="valor").reset_index()
def reentrenos(ax):
    for r in re.itertuples():
        ax.axvline(r.paso, color="#0aac23" if r.decision == "aprobada" else GRIS, ls="-" if r.decision == "aprobada" else "--", lw=1.4)
        ax.text(r.paso + .1, ax.get_ylim()[0], f"paso {r.paso}\\n{r.decision}\\nv{r.challenger_version}", fontsize=7, va="bottom", color="#191919")
print(len(mon), "métricas,", len(al), "alertas,", len(re), "reentrenamientos")''',
    "md:## 1. Umbral de desempeño: la CV del PSet 3 a escala semanal",
    '''c = U["desempeno"]["comparacion"]
display(pd.DataFrame({k: {"valor": v["valor"], "semanas OOF bajo el umbral": v["semanas_oof_bajo_umbral"],
                          "lotes sin alterar bajo el umbral": v["lotes_prueba_sin_alterar_bajo_umbral"]} for k, v in c.items()}).T)
print(f"AUC-PR semanal OOF: {U['desempeno']['auc_pr_semanal_media']:.4f} ± {U['desempeno']['auc_pr_semanal_desviacion']:.4f} -> umbral {U['desempeno']['umbral_auc_pr']:.4f}")
display(Image(D / "monitoreo/umbral_desempeno.png"))''',
    "md:## 2. Deriva de datos (PSI frente a la misma semana de 2019)",
    '''psi = mon[(mon.grupo == "datos") & (mon.metrica == "psi")].pivot_table(index="variable", columns="lote", values="valor")
psi = psi.loc[psi.max(axis=1).sort_values(ascending=False).index]
fig, ax = plt.subplots(figsize=(11, 4.6))
im = ax.imshow(psi.values, aspect="auto", cmap=plt.matplotlib.colors.LinearSegmentedColormap.from_list("azul", ["#ffffff", "#cce3fd", "#1b64be"]), vmin=0, vmax=.35)
ax.set_yticks(range(len(psi)), psi.index); ax.set_xticks(range(psi.shape[1]), psi.columns); ax.grid(False)
for i in range(psi.shape[0]):
    for j in range(psi.shape[1]):
        if psi.values[i, j] >= U["psi"]["aviso"]:
            ax.text(j, i, f"{psi.values[i, j]:.2f}", ha="center", va="center", fontsize=6, color="#ffffff" if psi.values[i, j] > .2 else "#191919")
fig.colorbar(im, ax=ax, label="PSI (aviso 0,10 · alerta 0,25)"); ax.set_xlabel("lote"); ax.set_title("PSI por variable y lote")
fig.tight_layout(); fig.savefig(D / "monitoreo/psi_por_lote.png", dpi=120); plt.show()
print("PSI máximo en lotes sin alterar (0-9):", round(psi.loc[:, :9].max().max(), 3), "| en lotes con D1:", round(psi.loc[:, 10:].max().max(), 3), "(", psi.loc[:, 10:].max(axis=1).idxmax(), ")")''',
    "md:## 3. Desempeño por lote etiquetado y reentrenamientos",
    '''fig, ax = plt.subplots(figsize=(11, 3.8))
for v, d in des.groupby("modelo_version"):
    ax.plot(d.lote, d.auc_pr, "o-", label=f"servido por v{v}", color={"1": MODELO, "4": REGLAS, "5": SIN_MODELO}.get(str(v), GRIS))
ax.axhline(U["desempeno"]["umbral_auc_pr"], color="#191919", ls=":", lw=1, label=f"umbral {U['desempeno']['umbral_auc_pr']:.4f}")
ax.set_ylim(0, 1.02); franjas(ax); reentrenos(ax)
ax.set_xlabel("lote (la etiqueta llega 2 pasos después; las líneas verticales marcan el paso de cada reentrenamiento)"); ax.set_ylabel("AUC-PR")
ax.legend(fontsize=8, loc="lower left"); ax.set_title("AUC-PR por lote etiquetado")
fig.tight_layout(); fig.savefig(D / "monitoreo/auc_pr_por_lote.png", dpi=120); plt.show()
display(re[["paso", "motivo", "lote_evaluacion", "champion_version", "challenger_version", "perdida_x1000_champion",
            "perdida_x1000_challenger", "mejora_x1000", "recomendacion", "decision"]].round(2))''',
    "md:## 4. Alertas\n\nLos lotes 0 a 9 no tienen ninguna alteración: cualquier alerta de severidad media o mayor ahí sería una falsa alarma.",
    '''orden = ["crítica", "alta", "media", "baja"]
t = al.pivot_table(index="paso", columns="severidad", values="id_alerta", aggfunc="count").reindex(columns=orden).fillna(0).reindex(range(26), fill_value=0)
fig, ax = plt.subplots(figsize=(11, 3.2)); base = np.zeros(len(t))
for s in orden[::-1]:
    ax.bar(t.index, t[s], bottom=base, color=SEV[s], label=s, edgecolor="#ffffff", linewidth=1.5); base += t[s].values
ax.set_xlabel("paso"); ax.set_ylabel("alertas"); ax.legend(fontsize=8, ncol=4); ax.set_title("Alertas por paso y severidad"); franjas(ax)
fig.tight_layout(); fig.savefig(D / "monitoreo/alertas_por_paso.png", dpi=120); plt.show()
sin_alt = al[(al.lote < 10) & (al.severidad != "baja")]
print("Falsas alarmas (severidad media o mayor) en lotes sin alterar:", len(sin_alt))
print("Avisos informativos en lotes sin alterar:", al[(al.lote < 10) & (al.severidad == "baja")][["paso", "variable", "valor"]].round(3).to_dict("records"))
display(al[al.severidad != "baja"].groupby(["id_alerta", "severidad"]).size().rename("veces").reset_index())''',
    "md:## 5. Resultado de negocio\n\nPérdida neta = fraude no detectado + USD 5 por falsa alarma. Se compara con las reglas fijas "
    "del PSet 1 y con no hacer nada (aprobar todo), lote por lote, con los reentrenamientos marcados.",
    '''n = des.assign(modelo=1000 * des.perdida_neta / des.filas, reglas=1000 * des.perdida_reglas / des.filas, sin_modelo=1000 * des.perdida_sin_modelo / des.filas)
fig, ax = plt.subplots(figsize=(11, 3.8))
ax.plot(n.lote, n.modelo, "o-", color=MODELO, label="modelo (champion vigente)"); ax.plot(n.lote, n.reglas, "o-", color=REGLAS, label="reglas fijas")
ax.plot(n.lote, n.sin_modelo, "o-", color=SIN_MODELO, label="sin modelo (aprobar todo)")
ax.set_yscale("log"); franjas(ax); reentrenos(ax); ax.set_ylabel("USD por 1.000 transacciones (log)"); ax.set_xlabel("lote etiquetado")
ax.legend(fontsize=8, loc="upper left"); ax.set_title("Pérdida neta por lote")
fig.tight_layout(); fig.savefig(D / "negocio/negocio_por_lote.png", dpi=120); plt.show()
acum = n[["perdida_neta", "perdida_reglas", "perdida_sin_modelo"]].cumsum()
fig, ax = plt.subplots(figsize=(11, 3.4))
for col, color, et in [("perdida_neta", MODELO, "modelo"), ("perdida_reglas", REGLAS, "reglas fijas"), ("perdida_sin_modelo", SIN_MODELO, "sin modelo")]:
    ax.plot(n.lote, acum[col] / 1000, "o-", color=color, label=et); ax.text(n.lote.iloc[-1] + .2, acum[col].iloc[-1] / 1000, f"{acum[col].iloc[-1]:,.0f}", fontsize=8, va="center")
franjas(ax); reentrenos(ax); ax.set_ylabel("miles de USD (acumulado)"); ax.set_xlabel("lote etiquetado"); ax.legend(fontsize=8); ax.set_title("Pérdida neta acumulada")
fig.tight_layout(); fig.savefig(D / "negocio/negocio_acumulado.png", dpi=120); plt.show()
tot = n[["perdida_neta", "perdida_reglas", "perdida_sin_modelo", "filas"]].sum()
print(f"Lotes 0-23 ({int(tot.filas):,} transacciones): modelo {tot.perdida_neta:,.0f} USD | reglas {tot.perdida_reglas:,.0f} USD | sin modelo {tot.perdida_sin_modelo:,.0f} USD")
print(f"Ahorro frente a las reglas: {1 - tot.perdida_neta / tot.perdida_reglas:.1%}; frente a no hacer nada: {1 - tot.perdida_neta / tot.perdida_sin_modelo:.1%}")
n[["lote", "modelo_version", "prevalencia", "auc_pr", "modelo", "reglas", "sin_modelo"]].round(3).to_csv(D / "negocio/negocio_por_lote.csv", index=False)''',
    "md:## 6. Ética: subgrupos y criterios de retirada",
    '''import etica
r = etica.main()
display(r["subgrupos"][["ventana", "dimension", "grupo", "transacciones", "fraudes", "auc_pr", "recall_pct", "falsas_alarmas_pct_legitimas",
                        "tasa_aprobar_pct", "tasa_verificar_pct", "tasa_retener_pct"]].round(3))
display(r["costos"][["error", "casos", "costo_usd", "quien_lo_asume"]].round(0))
display(r["criterios"][["criterio", "umbral", "observado", "se_activo"]])
display(Image(D / "etica/subgrupos.png"))''',
    "md:**Conclusiones.** Ver `docs/simulacion/resultados.md` y `docs/etica/etica.md`. La deriva de datos sola (D1) no "
    "disparó reentrenamientos y ningún lote sin alterar dio alertas de severidad media o mayor; la deriva conceptual (D2) "
    "hizo caer la AUC-PR y disparó 3 reentrenamientos (2 promovidos). El criterio de equidad R2 se activa: hay más falsas "
    "alarmas para las mujeres que para los hombres, y queda como hallazgo y revisión pendiente.",
]

if __name__ == "__main__":
    (RAIZ / "docs" / "negocio").mkdir(exist_ok=True)
    nbf.write(nb(N06), RAIZ / "notebooks" / "06_simulacion_produccion.ipynb")
    nbf.write(nb(N07), RAIZ / "notebooks" / "07_analisis_monitoreo.ipynb")
    print("notebooks 06 y 07 creados")
