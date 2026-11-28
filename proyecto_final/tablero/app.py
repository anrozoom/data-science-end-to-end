"""Tablero de monitoreo de Centinela, lote por lote (Streamlit).

Fuente de datos (FUENTE_DATOS): "auto" (por defecto) intenta Snowflake (CENTINELA.PRODUCCION, simulación vigente,
pasos 0 a 25) y, si no hay conexión, usa los CSV de docs/: monitoreo.csv, alertas.csv y
simulacion/reentrenamientos_simulacion.csv. "csv" fuerza los CSV; "snowflake" exige la conexión.
Umbrales: docs/monitoreo/umbrales.json. Reentrenamientos marcados en todos los gráficos por lote.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DOCS = Path(os.environ.get("DOCS_DIR", Path(__file__).resolve().parents[1] / "docs"))
FUENTE = os.environ.get("FUENTE_DATOS", "auto").lower()
N_LOTES, D1_DESDE, D2_DESDE = 26, 10, 14

# Paleta de referencia (skill de visualización): categórica en orden fijo; estados reservados para severidad.
MODELO, REGLAS, SIN_MODELO = "#257de0", "#f47230", "#00b894"
SEVERIDAD = {"crítica": "#dc3c3d", "alta": "#f18a59", "media": "#fbb315", "baja": "#9c9c9c"}
APROBADA, RECHAZADA = "#0aac23", "#666666"

st.set_page_config(page_title="Centinela · monitoreo", layout="wide")


# ------------------------------------------------------------------------------------ datos
def _snowflake() -> dict:
    import snowflake.connector
    con = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"], role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"], database=os.environ["SNOWFLAKE_DATABASE"], schema="PRODUCCION",
        authenticator="SNOWFLAKE_JWT", private_key_file=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", "/secrets/snowflake_key.p8"),
        private_key_file_pwd=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None, login_timeout=20)
    inicio = "(SELECT MAX(INICIO_UTC) FROM PRODUCCION.SIMULACION)"
    consultas = {
        "monitoreo": f"SELECT * FROM MONITOREO WHERE INICIO_SIMULACION = {inicio} AND PASO < {N_LOTES}",
        "alertas": f"SELECT * FROM ALERTAS WHERE INICIO_SIMULACION = {inicio} AND PASO < {N_LOTES}",
        "reentrenamientos": f"SELECT * FROM REENTRENAMIENTOS WHERE INICIO_SIMULACION = {inicio} AND PASO < {N_LOTES}",
    }
    out = {}
    for k, q in consultas.items():
        cur = con.cursor()
        cur.execute(q)
        d = cur.fetch_pandas_all()
        d.columns = [c.lower() for c in d.columns]
        out[k] = d
    con.close()
    return out


def _csv() -> dict:
    return {"monitoreo": pd.read_csv(DOCS / "monitoreo.csv"), "alertas": pd.read_csv(DOCS / "alertas.csv"),
            "reentrenamientos": pd.read_csv(DOCS / "simulacion" / "reentrenamientos_simulacion.csv")}


@st.cache_data(ttl=300, show_spinner="Cargando datos de monitoreo…")
def cargar(fuente: str) -> tuple[dict, str, str | None]:
    aviso = None
    if fuente in ("auto", "snowflake"):
        try:
            return _snowflake(), "Snowflake (CENTINELA.PRODUCCION)", None
        except Exception as e:  # noqa: BLE001 - sin conexión: CSV de docs/
            if fuente == "snowflake":
                raise
            aviso = (f"No se pudieron leer las tablas de la simulación en Snowflake ({type(e).__name__}: "
                     f"{str(e).splitlines()[0][:120]}); se usan los CSV de docs/ (exportes de la simulación completa).")
    return _csv(), "CSV de docs/", aviso


datos, origen, aviso = cargar(FUENTE)
U = json.loads((DOCS / "monitoreo" / "umbrales.json").read_text(encoding="utf-8"))
mon, al, re = datos["monitoreo"], datos["alertas"], datos["reentrenamientos"]
for d in (mon, al, re):
    for c in ("paso", "lote"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").astype("Int64")
mon["modelo_version"] = mon["modelo_version"].astype(str)


def serie(grupo: str, metricas: list[str], variable: str | None = None) -> pd.DataFrame:
    d = mon[(mon["grupo"] == grupo) & mon["metrica"].isin(metricas)]
    if variable is not None:
        d = d[d["variable"] == variable]
    return d.pivot_table(index=["lote", "modelo_version"], columns="metrica", values="valor").reset_index().sort_values("lote")


# ------------------------------------------------------------------------- capas comunes
re = re.assign(etiqueta=lambda r: "paso " + r["paso"].astype(str) + ": " + r["motivo"] + " → " + r["decision"]
               + " (v" + r["challenger_version"].astype(str) + ")")


def capas_contexto(eje_x: str = "lote") -> list:
    """Franjas de deriva (D1 desde el lote 10, D2 desde el 14) y reglas verticales en cada reentrenamiento."""
    franjas = pd.DataFrame({"x0": [D1_DESDE - 0.5, D2_DESDE - 0.5], "x1": [D2_DESDE - 0.5, N_LOTES - 0.5],
                            "deriva": ["D1 (datos)", "D1 + D2 (concepto)"]})
    f = alt.Chart(franjas).mark_rect(opacity=0.07, color="#666666").encode(x=f"x0:Q", x2="x1:Q", tooltip=["deriva"])
    r = alt.Chart(re).mark_rule(strokeWidth=2).encode(
        x=alt.X("paso:Q", title=eje_x),
        color=alt.Color("decision:N", scale=alt.Scale(domain=["aprobada", "rechazada"], range=[APROBADA, RECHAZADA]),
                        legend=alt.Legend(title="reentrenamiento", orient="bottom")),
        strokeDash=alt.condition(alt.datum.decision == "aprobada", alt.value([1, 0]), alt.value([4, 3])),
        tooltip=[alt.Tooltip("etiqueta:N", title="reentrenamiento"), alt.Tooltip("mejora_x1000:Q", format=".2f", title="mejora/1000")])
    return [f, r]


def linea(df: pd.DataFrame, columnas: dict, titulo_y: str, umbrales: list[tuple] = (), escala_log: bool = False,
          dominio_y=None) -> alt.Chart:
    largo = df.melt(id_vars=["lote", "modelo_version"], value_vars=list(columnas), var_name="serie", value_name="valor")
    largo["serie"] = largo["serie"].map({k: v[0] for k, v in columnas.items()})
    y = alt.Y("valor:Q", title=titulo_y, scale=alt.Scale(type="log" if escala_log else "linear",
                                                         **({"domain": dominio_y} if dominio_y else {})))
    base = alt.Chart(largo).encode(
        x=alt.X("lote:Q", title="lote (semana)", scale=alt.Scale(domain=[-0.5, N_LOTES - 0.5])), y=y,
        color=alt.Color("serie:N", scale=alt.Scale(domain=[v[0] for v in columnas.values()], range=[v[1] for v in columnas.values()]),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=["lote:Q", "serie:N", alt.Tooltip("valor:Q", format=",.4f"), alt.Tooltip("modelo_version:N", title="versión")])
    capas = capas_contexto() + [base.mark_line(strokeWidth=2), base.mark_point(size=60, filled=True)]
    for valor, texto in umbrales:
        u = pd.DataFrame({"y": [valor], "t": [texto]})
        capas.append(alt.Chart(u).mark_rule(color="#191919", strokeDash=[2, 2], strokeWidth=1).encode(y="y:Q", tooltip="t:N"))
    return alt.layer(*capas).properties(height=280).resolve_scale(color="independent")


# ----------------------------------------------------------------------------------- página
st.title("Centinela · monitoreo de la simulación de producción")
st.caption(f"Fuente: **{origen}** · 26 lotes semanales (jul-dic 2020) · el target de un lote llega 2 pasos después · "
           f"franjas grises: deriva inducida (D1 desde el lote {D1_DESDE}, D2 desde el {D2_DESDE}) · "
           "líneas verticales: reentrenamientos (continua = aprobada, punteada = rechazada)")
if aviso:
    st.warning(aviso)

sistema = serie("sistema", ["latencia_online_p50_ms", "latencia_online_p95_ms", "volumen", "volumen_relativo_2019",
                            "errores_4xx", "errores_5xx", "solicitudes"])
modelo = serie("modelo", ["tasa_aprobar", "tasa_verificar", "tasa_retener", "tasa_alertas", "prob_p95", "respaldo_pct"])
des = serie("desempeño", ["auc_pr", "perdida_x1000", "perdida_neta", "perdida_reglas", "perdida_sin_modelo", "filas",
                          "prevalencia", "recall"])
des["reglas_x1000"] = 1000 * des["perdida_reglas"] / des["filas"]
des["sin_modelo_x1000"] = 1000 * des["perdida_sin_modelo"] / des["filas"]

k = st.columns(5)
k[0].metric("Transacciones servidas", f"{int(sistema['volumen'].sum()):,}".replace(",", "."))
k[1].metric("Champion en el último lote", f"v{sistema['modelo_version'].iloc[-1]}")
k[2].metric("Pérdida del modelo (lotes etiquetados)", f"USD {des['perdida_neta'].sum():,.0f}".replace(",", "."))
k[3].metric("Pérdida de las reglas fijas", f"USD {des['perdida_reglas'].sum():,.0f}".replace(",", "."))
k[4].metric("Alertas de severidad media o mayor", int((al["severidad"] != "baja").sum()))

pest = st.tabs(["Desempeño y negocio", "Deriva de datos", "Modelo", "Sistema", "Alertas", "Reentrenamientos"])

with pest[0]:
    st.subheader("AUC-PR del lote etiquetado")
    st.altair_chart(linea(des, {"auc_pr": ("AUC-PR", MODELO)}, "AUC-PR",
                          [(U["desempeno"]["umbral_auc_pr"], f"umbral {U['desempeno']['umbral_auc_pr']:.4f} (CV semanal)")],
                          dominio_y=[0, 1]), use_container_width=True)
    st.subheader("Pérdida neta por 1.000 transacciones (escala logarítmica)")
    st.altair_chart(linea(des, {"perdida_x1000": ("modelo", MODELO), "reglas_x1000": ("reglas fijas", REGLAS),
                                "sin_modelo_x1000": ("sin modelo", SIN_MODELO)}, "USD por 1.000 transacciones",
                          escala_log=True), use_container_width=True)
    t = des[["lote", "modelo_version", "prevalencia", "auc_pr", "recall", "perdida_x1000", "reglas_x1000", "sin_modelo_x1000"]]
    st.dataframe(t.rename(columns={"modelo_version": "versión"}).round(4), hide_index=True, use_container_width=True)

with pest[1]:
    psi = mon[(mon["grupo"] == "datos") & (mon["metrica"] == "psi")]
    st.subheader("PSI por variable y lote (referencia: misma semana de 2019)")
    st.caption(f"Aviso ≥ {U['psi']['aviso']}, alerta ≥ {U['psi']['alerta']}. Excluidas: {', '.join(U['psi']['excluidas'])} "
               "(ver docs/simulacion/diseno_deriva.md).")
    mapa = alt.Chart(psi).mark_rect(stroke="#ffffff", strokeWidth=2).encode(
        x=alt.X("lote:O", title="lote"), y=alt.Y("variable:N", title=None, sort="-color"),
        color=alt.Color("valor:Q", title="PSI", scale=alt.Scale(domain=[0, 0.35], range=["#cce3fd", "#1b64be"], clamp=True)),
        tooltip=["lote", "variable", alt.Tooltip("valor:Q", format=".3f", title="PSI"), "estado"])
    st.altair_chart(mapa.properties(height=420), use_container_width=True)
    var = st.selectbox("Variable", sorted(psi["variable"].unique()), index=sorted(psi["variable"].unique()).index("categoria"))
    st.altair_chart(linea(serie("datos", ["psi"], var), {"psi": (f"PSI de {var}", MODELO)}, "PSI",
                          [(U["psi"]["aviso"], "aviso 0,10"), (U["psi"]["alerta"], "alerta 0,25")]), use_container_width=True)

with pest[2]:
    st.subheader("Tasa de cada decisión")
    st.altair_chart(linea(modelo, {"tasa_verificar": ("verificar", REGLAS), "tasa_retener": ("retener", MODELO)},
                          "proporción del lote"), use_container_width=True)
    st.subheader("Tasa de alertas (verificar + retener) y su banda de la CV")
    st.altair_chart(linea(modelo, {"tasa_alertas": ("tasa de alertas", MODELO)}, "proporción del lote",
                          [(U["tasa_alertas"]["banda_min"], "banda mínima"), (U["tasa_alertas"]["banda_max"], "banda máxima")]),
                    use_container_width=True)
    st.subheader("Percentil 95 de la probabilidad")
    st.altair_chart(linea(modelo, {"prob_p95": ("p95 de la probabilidad", MODELO)}, "probabilidad"), use_container_width=True)

with pest[3]:
    st.subheader("Latencia de POST /predecir (ms)")
    st.altair_chart(linea(sistema, {"latencia_online_p50_ms": ("p50", MODELO), "latencia_online_p95_ms": ("p95", REGLAS)},
                          "ms", [(200, "umbral SIS-LAT 200 ms")]), use_container_width=True)
    st.subheader("Volumen frente a la misma semana de 2019")
    st.altair_chart(linea(sistema, {"volumen_relativo_2019": ("volumen relativo", MODELO)}, "lote / 2019",
                          [(0.7, "banda 0,70"), (1.3, "banda 1,30")]), use_container_width=True)
    st.dataframe(sistema.rename(columns={"modelo_version": "versión"}).round(2), hide_index=True, use_container_width=True)

with pest[4]:
    st.subheader("Alertas por paso y severidad")
    orden = ["crítica", "alta", "media", "baja"]
    barras = alt.Chart(al).mark_bar(stroke="#ffffff", strokeWidth=2, cornerRadiusEnd=4).encode(
        x=alt.X("paso:O", title="paso"), y=alt.Y("count():Q", title="alertas"),
        color=alt.Color("severidad:N", scale=alt.Scale(domain=orden, range=[SEVERIDAD[s] for s in orden]),
                        legend=alt.Legend(title="severidad", orient="top")),
        order=alt.Order("severidad:N"), tooltip=["paso", "severidad", "id_alerta", "count()"])
    st.altair_chart(barras.properties(height=260), use_container_width=True)
    sev = st.multiselect("Severidad", orden, default=["crítica", "alta", "media"])
    cols = [c for c in ["paso", "lote", "severidad", "id_alerta", "variable", "valor", "umbral", "receptor", "accion"] if c in al.columns]
    st.dataframe(al[al["severidad"].isin(sev)][cols].sort_values(["paso", "severidad"]), hide_index=True, use_container_width=True)

with pest[5]:
    st.subheader("Reentrenamientos (regla: mejora en pérdida/1.000 > 4,51)")
    cols = [c for c in ["paso", "motivo", "lote_evaluacion", "champion_version", "challenger_version", "perdida_x1000_champion",
                        "perdida_x1000_challenger", "mejora_x1000", "recomendacion", "decision", "motivo_decision"] if c in re.columns]
    st.dataframe(re[cols].round(2), hide_index=True, use_container_width=True)
