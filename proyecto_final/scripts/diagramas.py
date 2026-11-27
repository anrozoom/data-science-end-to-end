"""Dibuja docs/arquitectura.png y docs/modelo_dimensional.png (matplotlib; sin graphviz ni Mermaid en el Codespace).
Uso, desde proyecto_final/:  python scripts/diagramas.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
TINTA, GRIS = "#191919", "#666666"
AZUL, NARANJA, AQUA, VIOLETA = "#257de0", "#f47230", "#00b894", "#6a4ce2"


def caja(ax, x, y, w, h, titulo, detalle="", color=AZUL, relleno="#ffffff", fs=8.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12", fc=relleno, ec=color, lw=1.6))
    ax.text(x + w / 2, y + h - 0.2, titulo, ha="center", va="top", fontsize=fs, weight="bold", color=TINTA)
    if detalle:
        ax.text(x + w / 2, y + h - 0.52, detalle, ha="center", va="top", fontsize=6.6, color=GRIS, linespacing=1.3)
    return (x, y, w, h)


def grupo(ax, x, y, w, h, titulo, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.2", fc=color, ec=color, alpha=0.08, lw=0))
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.2", fc="none", ec=color, lw=1, ls="--"))
    ax.text(x + 0.15, y + h - 0.12, titulo, ha="left", va="top", fontsize=8, color=color, weight="bold")


def flecha(ax, a, b, texto="", lado="d", color=TINTA, curva=0.0, dx=0, dy=0):
    (xa, ya, wa, ha), (xb, yb, wb, hb) = a, b
    ini = {"d": (xa + wa, ya + ha / 2), "b": (xa + wa / 2, ya), "a": (xa + wa / 2, ya + ha), "i": (xa, ya + ha / 2)}[lado[0]]
    fin = {"d": (xb + wb, yb + hb / 2), "b": (xb + wb / 2, yb), "a": (xb + wb / 2, yb + hb), "i": (xb, yb + hb / 2)}[lado[1]]
    ax.add_patch(FancyArrowPatch(ini, fin, arrowstyle="-|>", mutation_scale=11, lw=1.2, color=color,
                                 connectionstyle=f"arc3,rad={curva}"))
    if texto:
        ax.text((ini[0] + fin[0]) / 2 + dx, (ini[1] + fin[1]) / 2 + dy, texto, fontsize=6.4, color=color, ha="center",
                va="center", bbox=dict(fc="#ffffff", ec="none", pad=0.6))


def ruta(ax, puntos, texto="", en=None, color=TINTA, ha="center"):
    """Flecha ortogonal por los puntos dados (la punta en el último); texto opcional en la posición en."""
    xs, ys = zip(*puntos)
    ax.plot(xs[:-1], ys[:-1], color=color, lw=1.2, solid_joinstyle="round")
    ax.add_patch(FancyArrowPatch(puntos[-2], puntos[-1], arrowstyle="-|>", mutation_scale=11, lw=1.2, color=color))
    if texto:
        ax.text(*en, texto, fontsize=6.6, color=color, ha=ha, va="center", bbox=dict(fc="#ffffff", ec="none", pad=0.8))


def arquitectura():
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 16); ax.set_ylim(0, 10); ax.axis("off")
    ax.text(0.2, 9.9, "Centinela · arquitectura de punta a punta (proyecto final)", fontsize=13, weight="bold", va="top", color=TINTA)
    ax.text(0.2, 9.5, "Un solo comando: docker compose up -d  (Kestra + Postgres, Spark, MLflow, API, tablero). Patrón de despliegue: ONLINE "
            "(la decisión se toma en la autorización).", fontsize=8.5, va="top", color=GRIS)
    grupo(ax, 2.0, 0.2, 9.75, 8.95, "docker-compose.yml (Codespace: 4 núcleos, 16 GB)", AZUL)
    grupo(ax, 11.95, 3.4, 3.85, 5.75, "Snowflake · CENTINELA (par de llaves)", AQUA)
    grupo(ax, 11.95, 0.2, 3.85, 2.95, "GitHub", VIOLETA)

    fuente = caja(ax, 0.2, 7.0, 1.6, 1.0, "Kaggle", "Sparkov CC0\n1.852.394 filas", GRIS)
    caja(ax, 2.3, 7.0, 2.5, 1.35, "Kestra · ingesta.yml", "Schedule diario, retries, backfill\ncargar_raw → dbt → Spark → validar\n(una sola ejecución)", NARANJA)
    caja(ax, 5.2, 7.0, 2.6, 1.35, "dbt Core (Docker)", "BRONZE → SILVER → GOLD\nstar schema, 67 tests", NARANJA)
    caja(ax, 8.2, 7.0, 3.1, 1.35, "Spark 3.5 (master + worker)", "GOLD → OBT, ventanas sin fuga\nvalidación de joins", NARANJA)
    caja(ax, 12.2, 6.6, 3.35, 1.95, "RAW · BRONZE · SILVER · GOLD · OBT", "TRANSACCIONES_OBT\n1.852.394 filas, 40 columnas\nhuella = snapshot del PSet 3", AQUA)
    caja(ax, 12.2, 3.65, 3.35, 2.6, "PRODUCCION", "LOTES · TARGETS · TARGETS_LLEGADOS\nPREDICCIONES · SOLICITUDES\nMONITOREO · ALERTAS\nREENTRENAMIENTOS · SIMULACION", AQUA)
    caja(ax, 2.3, 4.85, 2.5, 1.45, "Snapshot Parquet", "src/datos.py\nSHA-256 9be410f7…\n(fuera de git)", GRIS)
    caja(ax, 5.2, 4.85, 2.6, 1.45, "Experimentación", "notebooks 01-05, src/pipeline.py\nCV temporal, 5 familias,\n93 corridas de tuning", AZUL)
    caja(ax, 8.2, 4.85, 3.1, 1.45, "MLflow 2.17 (:5055)", "tracking + Model Registry\ncentinela-modelo\n@champion / @challenger", AZUL)
    caja(ax, 2.3, 2.5, 2.5, 1.75, "Kestra · produccion_lotes", "26 lotes semanales\n(deriva D1 y D2)\ntarget 2 lotes después", NARANJA)
    caja(ax, 5.2, 2.5, 2.6, 1.75, "Kestra · monitoreo", "PSI, KS, chi², latencia,\nAUC-PR, pérdida neta,\nalertas (catálogo)", NARANJA)
    caja(ax, 8.2, 2.5, 3.1, 1.75, "API FastAPI (:8000)", "/predecir · /predecir_lote · /modelo\nresuelve @champion cada 30 s\nrespaldo = reglas del PSet 1\nregistra cada predicción", AZUL)
    caja(ax, 2.3, 0.55, 2.5, 1.5, "Tablero Streamlit (:8501)", "lote por lote: sistema,\nmodelo, deriva, negocio\n(Snowflake o CSV de docs/)", AZUL)
    caja(ax, 5.2, 0.55, 2.6, 1.5, "Kestra · reentrenamiento", "src/reentrenar.py\nPAUSA de aprobación humana\npromoción o rechazo", NARANJA)
    caja(ax, 12.2, 1.55, 3.35, 1.25, "Actions: ci.yml / cd.yml", "pytest: contrato, modelo,\ncomportamiento, respaldo, monitoreo", VIOLETA)
    caja(ax, 12.2, 0.4, 3.35, 0.9, "GHCR", "ghcr.io/…/centinela-api:<sha>", VIOLETA)

    ruta(ax, [(1.8, 7.5), (2.3, 7.5)], "una vez", (2.05, 8.2))
    ruta(ax, [(4.8, 7.675), (5.2, 7.675)]); ruta(ax, [(7.8, 7.675), (8.2, 7.675)])
    ruta(ax, [(3.55, 8.35), (3.55, 8.7), (13.875, 8.7), (13.875, 8.55)], "COPY a RAW, idempotente por día", (8.6, 8.7))
    ruta(ax, [(11.3, 7.5), (12.2, 7.5)], "OBT", (11.75, 7.75))
    ruta(ax, [(12.2, 6.8), (11.55, 6.8), (11.55, 6.65), (3.55, 6.65), (3.55, 6.3)], "snapshot de la OBT (src/datos.py)", (7.5, 6.65))
    ruta(ax, [(4.8, 5.575), (5.2, 5.575)]); ruta(ax, [(7.8, 5.575), (8.2, 5.575)])
    ruta(ax, [(9.75, 4.85), (9.75, 4.25)], "carga @champion", (10.55, 4.7))
    ruta(ax, [(12.2, 4.4), (11.6, 4.4), (11.6, 4.42), (3.55, 4.42), (3.55, 4.25)], "lee el lote k (PRODUCCION.LOTES)", (6.4, 4.42))
    ruta(ax, [(11.3, 3.75), (12.2, 3.75)])
    ruta(ax, [(4.8, 3.375), (5.2, 3.375)])
    ruta(ax, [(4.2, 2.5), (4.2, 2.27), (9.0, 2.27), (9.0, 2.5)], "POST /predecir(_lote)", (7.15, 2.27))
    ruta(ax, [(6.5, 2.5), (6.5, 2.05)], "disparo", (5.95, 2.27))
    ruta(ax, [(7.8, 1.3), (8.0, 1.3), (8.0, 5.2), (8.2, 5.2)], "nueva versión → @challenger;\naprobada → @champion", (9.5, 1.7))
    ruta(ax, [(12.2, 3.9), (11.75, 3.9), (11.75, 0.35), (3.55, 0.35), (3.55, 0.55)], "MONITOREO, ALERTAS, REENTRENAMIENTOS", (8.6, 0.35))
    ruta(ax, [(13.875, 1.55), (13.875, 1.3)])
    ruta(ax, [(12.2, 0.85), (11.5, 0.85), (11.5, 2.9), (11.3, 2.9)], "imagen", (10.95, 1.05))
    fig.savefig(RAIZ / "docs" / "arquitectura.png", dpi=130, bbox_inches="tight"); plt.close(fig)


def tabla_er(ax, x, y, nombre, filas, color, ancho=3.0):
    alto = 0.32 * (len(filas) + 1) + 0.1
    ax.add_patch(FancyBboxPatch((x, y - alto), ancho, alto, boxstyle="round,pad=0.02,rounding_size=0.08", fc="#ffffff", ec=color, lw=1.6))
    ax.add_patch(FancyBboxPatch((x, y - 0.42), ancho, 0.42, boxstyle="round,pad=0.02,rounding_size=0.08", fc=color, ec=color, lw=1.6))
    ax.text(x + ancho / 2, y - 0.21, nombre, ha="center", va="center", fontsize=9, weight="bold", color="#ffffff")
    for i, (col, tipo) in enumerate(filas):
        ax.text(x + 0.12, y - 0.65 - 0.32 * i, col, fontsize=7.2, va="center", color=TINTA,
                weight="bold" if tipo in ("PK", "FK") else "normal")
        ax.text(x + ancho - 0.12, y - 0.65 - 0.32 * i, tipo, fontsize=6.6, va="center", ha="right", color=GRIS)
    return (x, y - alto, ancho, alto)


def modelo_dimensional():
    fig, ax = plt.subplots(figsize=(15, 9.4))
    ax.set_xlim(0, 15); ax.set_ylim(0, 9.4); ax.axis("off")
    ax.text(0.2, 9.3, "Centinela · star schema (GOLD, dbt)", fontsize=13, weight="bold", va="top", color=TINTA)
    ax.text(0.2, 8.9, "Grano del hecho: una fila por transacción con tarjeta (trans_num), la unidad de predicción del PSet 1. "
            "Claves sustitutas md5() de la clave natural. 67 tests en dbt build.", fontsize=8.5, va="top", color=GRIS)
    fct = tabla_er(ax, 5.9, 6.9, "fct_transacciones · 1.852.394", [
        ("trans_num", "PK"), ("fecha_sk", "FK"), ("hora_sk", "FK"), ("cliente_sk", "FK"), ("comercio_sk", "FK"), ("categoria_sk", "FK"),
        ("trans_ts / trans_epoch", "timestamp"), ("amt", "medida"), ("merch_lat / merch_long", "cambia por tx"),
        ("distancia_km", "medida (haversine)"), ("edad_en_transaccion", "number"), ("es_menor_de_edad", "boolean"),
        ("is_fraud", "target"), ("source_file", "auditoría")], NARANJA, ancho=3.3)
    cli = tabla_er(ax, 0.4, 8.2, "dim_cliente · 999", [("cliente_sk", "PK"), ("cc_num", "UK"), ("first / last_name", "no se usa"),
        ("gender", "auditoría de equidad"), ("street, city, state, zip", ""), ("lat / long, city_pop", ""), ("job, dob", ""),
        ("primera_transaccion", ""), ("n_transacciones", "")], AZUL)
    com = tabla_er(ax, 11.5, 8.2, "dim_comercio · 693", [("comercio_sk", "PK"), ("comercio", "UK (sin 'fraud_')"),
        ("n_categorias", ""), ("es_multicategoria", "boolean"), ("n_transacciones", "")], AZUL)
    cat = tabla_er(ax, 11.5, 5.4, "dim_categoria · 14", [("categoria_sk", "PK"), ("categoria", "UK"), ("canal", "en_linea / presencial")], AZUL)
    fec = tabla_er(ax, 0.4, 4.3, "dim_fecha · 731", [("fecha_sk", "PK (AAAAMMDD)"), ("fecha", "UK"), ("anio, trimestre, mes, dia", ""),
        ("dia_semana, es_fin_de_semana", ""), ("particion_temporal", "entren. / prueba")], AZUL)
    hor = tabla_er(ax, 11.5, 3.3, "dim_hora · 24", [("hora_sk", "PK (0-23)"), ("hora", ""), ("es_nocturna", "22-04, regla fija"), ("franja", "")], AZUL)
    for d, lado in [(cli, "id"), (fec, "id"), (com, "di"), (cat, "di"), (hor, "di")]:
        (xf, yf, wf, hf), (xd, yd, wd, hd) = fct, d
        a = (xf, yf + hf / 2) if lado == "id" else (xf + wf, yf + hf / 2)
        b = (xd + wd, yd + hd / 2) if lado == "id" else (xd, yd + hd / 2)
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-", lw=1.2, color=GRIS, connectionstyle="arc3,rad=0.05"))
        ax.text(a[0] + (b[0] - a[0]) * 0.18, a[1] + (b[1] - a[1]) * 0.18 + 0.12, "N", fontsize=7, color=GRIS)
        ax.text(a[0] + (b[0] - a[0]) * 0.85, a[1] + (b[1] - a[1]) * 0.85 + 0.12, "1", fontsize=7, color=GRIS)
    ax.text(5.9, 1.55, "Después de GOLD: Spark une el hecho con las 5 dimensiones y calcula las ventanas por cliente\n"
            "(n_tx_1h, gasto_24h, segundos_desde_anterior, monto_relativo…) solo con el pasado → OBT.TRANSACCIONES_OBT\n"
            "(una fila por transacción; conteo y tasa de fraude validados = hecho).", fontsize=7.6, color=GRIS, va="top")
    fig.savefig(RAIZ / "docs" / "modelo_dimensional.png", dpi=130, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    arquitectura()
    modelo_dimensional()
    print("docs/arquitectura.png y docs/modelo_dimensional.png")
