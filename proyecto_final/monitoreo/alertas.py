"""Catálogo de alertas de Centinela y su evaluación por paso de la simulación.

Plantilla de cada alerta: métrica | umbral | ventana | severidad | quién la recibe | acción.
Canal: el log de la ejecución de Kestra (monitoreo.yml, nivel WARN o ERROR según la severidad), la tabla
CENTINELA.PRODUCCION.ALERTAS y docs/alertas.csv. Correo o Slack quedan fuera (sin servidor de correo en el
Codespace); se agregarían con una tarea de notificación de Kestra sobre la misma salida.

Umbrales (docs/monitoreo/umbrales.json, calibrados SOLO con la CV del PSet 3, salvo los de sistema, que son
de negocio):
  - desempeño: AUC-PR < media - 2 desv. de la AUC-PR OOF semanal de la CV del champion.
  - tasa de alertas: fuera de media ± 3 desv. de la tasa semanal OOF (capacidad de los analistas).
  - PSI: 0,10 aviso y 0,25 alerta (estándar de la industria); referencia: misma semana de 2019.
  - latencia p95 de /predecir: 200 ms (presupuesto del paso de puntaje dentro de la autorización).
  - volumen: ±30 % frente a la misma semana de 2019 (la variación natural medida va de 0,85 a 1,04).
"""
from __future__ import annotations

import pandas as pd

SEVERIDADES = ["crítica", "alta", "media", "baja"]

PLANTILLA = pd.DataFrame([
    # id, métrica, umbral, ventana, severidad, receptor, acción
    ("SIS-LAT", "latencia p95 de POST /predecir (ms)", "> 200 ms", "lote (semana)", "media",
     "plataforma (MLOps)", "revisar CPU y memoria de la API; escalar réplicas"),
    ("SIS-5XX", "tasa de respuestas 5xx", "> 0,1 % de las solicitudes", "lote (semana)", "alta",
     "plataforma (MLOps)", "revisar logs de la API; si persiste, activar el interruptor de respaldo"),
    ("SIS-4XX", "tasa de respuestas 4xx", "> 1 % de las solicitudes", "lote (semana)", "media",
     "integración (sistema autorizador)", "revisar el contrato: el mensaje 422 dice qué campo falla"),
    ("SIS-VOL", "volumen del lote / misma semana de 2019", "fuera de [0,70; 1,30]", "lote (semana)", "media",
     "datos y negocio", "confirmar si el tráfico cambió de verdad o si falló la ingesta"),
    ("DAT-SOP", "% de filas fuera del soporte de entrenamiento (alguna numérica)", "> 1 %", "lote (semana)", "media",
     "modelos", "revisar los casos: el modelo extrapola fuera de lo que vio (hallazgo de montos fuera de soporte)"),
    ("DAT-CAT", "categorías no vistas en entrenamiento", "> 0", "lote (semana)", "alta",
     "datos", "actualizar los catálogos y reentrenar; mientras tanto la API las rechaza con 422"),
    ("DAT-NUL", "nulos en variables opcionales", "> tasa de entrenamiento + 5 pp", "lote (semana)", "media",
     "datos", "revisar el cálculo del historial del cliente en el pipeline"),
    ("DAT-PSI-AVISO", "PSI de una variable vigilada", ">= 0,10 y < 0,25", "lote vs. misma semana de 2019", "baja",
     "datos", "observar la tendencia en los lotes siguientes"),
    ("DAT-PSI", "PSI de una variable vigilada", ">= 0,25", "lote vs. misma semana de 2019", "media",
     "datos y modelos", "diagnosticar con KS / chi-cuadrado; la deriva de datos sola NO reentrena"),
    ("MOD-TASA", "tasa de alertas (verificar + retener)", "fuera de la banda semanal OOF (media ± 3 desv.)",
     "lote (semana)", "media", "operaciones de fraude (analistas)",
     "ajustar la capacidad de verificación; revisar si cambió la prevalencia"),
    ("MOD-DES-1", "AUC-PR del lote etiquetado", "< umbral semanal de la CV", "lote etiquetado (target 2 pasos después)",
     "alta", "modelos y riesgo de fraude", "revisar el lote; si se repite en el lote siguiente, se reentrena"),
    ("MOD-DES-2", "AUC-PR de 2 lotes consecutivos del champion vigente", "< umbral semanal de la CV en ambos",
     "2 lotes etiquetados", "crítica", "modelos y riesgo de fraude (aprueba)",
     "dispara reentrenamiento.yml; la promoción espera la aprobación humana (Pause)"),
    ("MOD-PERD", "pérdida neta del modelo frente a las reglas fijas", "pérdida del modelo > pérdida de las reglas",
     "lote etiquetado", "alta", "riesgo de fraude (negocio)",
     "criterio de retirada: evaluar volver a las reglas fijas con el interruptor de respaldo"),
], columns=["id", "metrica", "umbral", "ventana", "severidad", "receptor", "accion"])


def _alerta(id_: str, valor, umbral, variable: str | None = None, detalle: str = "") -> dict:
    fila = PLANTILLA.set_index("id").loc[id_]
    return {"id_alerta": id_, "metrica": fila["metrica"], "variable": variable, "valor": None if valor is None else float(valor),
            "umbral": str(umbral), "ventana": fila["ventana"], "severidad": fila["severidad"],
            "receptor": fila["receptor"], "accion": fila["accion"],
            "mensaje": f"[{fila['severidad'].upper()}] {id_} {fila['metrica']}{' (' + variable + ')' if variable else ''}"
                       f" = {valor if not isinstance(valor, float) else round(valor, 4)} | umbral {umbral}"
                       f"{' | ' + detalle if detalle else ''} -> {fila['receptor']}: {fila['accion']}"}


def evaluar(m: dict, u: dict) -> list[dict]:
    """m: métricas del paso (monitorear.py). u: umbrales.json. Devuelve las alertas disparadas."""
    a = []
    s = m["sistema"]
    if s.get("latencia_online_p95_ms") is not None and s["latencia_online_p95_ms"] > 200:
        a.append(_alerta("SIS-LAT", s["latencia_online_p95_ms"], "200 ms"))
    if s["solicitudes"] and s["errores_5xx"] / s["solicitudes"] > 0.001:
        a.append(_alerta("SIS-5XX", s["errores_5xx"] / s["solicitudes"], "0,1 %"))
    if s["solicitudes"] and s["errores_4xx"] / s["solicitudes"] > 0.01:
        a.append(_alerta("SIS-4XX", s["errores_4xx"] / s["solicitudes"], "1 %"))
    lo, hi = u["volumen"]["banda_relativa_misma_semana_2019"]
    if s.get("volumen_relativo_2019") is not None and not lo <= s["volumen_relativo_2019"] <= hi:
        a.append(_alerta("SIS-VOL", s["volumen_relativo_2019"], f"[{lo}; {hi}]",
                         detalle=f"{s['volumen']} transacciones frente a {s['volumen_2019']} en 2019"))

    d = m["datos"]
    for v, pct in d["fuera_de_soporte_pct"].items():
        if pct > 100 * u["datos"]["fuera_de_soporte_max"]:
            a.append(_alerta("DAT-SOP", pct, "1 %", variable=v))
    if d["categorias_no_vistas"] > 0:
        a.append(_alerta("DAT-CAT", d["categorias_no_vistas"], "0"))
    for v, pct in d["nulos_pct"].items():
        if pct > 100 * u["nulos_referencia"].get(v, 0) + 5:
            a.append(_alerta("DAT-NUL", pct, f"{100 * u['nulos_referencia'].get(v, 0) + 5:.2f} %", variable=v))
    for f in d["psi"]:
        if f["estado"] == "alerta":
            a.append(_alerta("DAT-PSI", f["psi"], u["psi"]["alerta"], variable=f["variable"],
                             detalle=f"{f['prueba']} p = {f['valor_p']:.2g}"))
        elif f["estado"] == "aviso":
            a.append(_alerta("DAT-PSI-AVISO", f["psi"], u["psi"]["aviso"], variable=f["variable"]))

    mo = m["modelo"]
    if mo.get("tasa_alertas") is not None and not u["tasa_alertas"]["banda_min"] <= mo["tasa_alertas"] <= u["tasa_alertas"]["banda_max"]:
        a.append(_alerta("MOD-TASA", mo["tasa_alertas"],
                         f"[{u['tasa_alertas']['banda_min']:.4f}; {u['tasa_alertas']['banda_max']:.4f}]"))

    e = m.get("etiquetado")
    if e and e.get("auc_pr") is not None:
        if e["auc_pr"] < u["desempeno"]["umbral_auc_pr"]:
            a.append(_alerta("MOD-DES-1", e["auc_pr"], round(u["desempeno"]["umbral_auc_pr"], 4),
                             detalle=f"lote {e['lote']} servido por la versión {e['version']}"))
        if e["perdida_neta"] > e["perdida_reglas"]:
            a.append(_alerta("MOD-PERD", e["perdida_neta"], f"pérdida de las reglas = {e['perdida_reglas']:.0f} USD",
                             detalle=f"lote {e['lote']}"))
    if m["disparo"]["motivo"] == "desempeño":
        a.append(_alerta("MOD-DES-2", max(m["disparo"]["auc_lotes"]), round(u["desempeno"]["umbral_auc_pr"], 4),
                         detalle=f"lotes {m['disparo']['lotes']} de la versión {m['disparo']['version']}, "
                                 f"AUC-PR {[round(x, 4) for x in m['disparo']['auc_lotes']]} (valor = la mayor)"))
    return a
