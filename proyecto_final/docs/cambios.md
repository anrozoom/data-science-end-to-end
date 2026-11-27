# Cambios respecto de los PSet 1 a 3

Cada fila indica la observación o decisión, qué se cambió y en qué archivo. Las entregas anteriores quedan intactas en sus carpetas y tags (`pset_2/` con `pset-02`, `pset_3/` con `pset-03`). El proyecto final copia lo necesario a `proyecto_final/`.

## 1. Observaciones del profesor

| PSet | Observación | Qué cambié | Dónde | Estado |
|---|---|---|---|---|
| 1 (9,7) | No se puede repetir el mismo protocolo de validación en el dataset real ULB/Worldline (`mlg-ulb/creditcardfraud`): no tiene las variables de distancia ni el historial del cliente | Se retira la validación externa con ULB del plan. Un contraste con ULB solo sería válido con variables compatibles (monto y hora relativa derivada de `Time`) o con otra fuente real con historial por tarjeta. Queda como limitación | `docs/cambios.md`, `docs/datos/limitaciones.md`, `README.md` (limitaciones) | Aplicado |
| 2 (Kestra 8,5) | "Integra dbt y Spark en el flujo. La ingesta, los reintentos y el backfill funcionan, pero las transformaciones aún se ejecutan manualmente." | `kestra/ingesta.yml` encadena en **una sola ejecución**, sin pasos manuales: carga por día a RAW (subflows concurrentes) → dbt (BRONZE → SILVER → GOLD, con tests) → Spark (OBT con sus validaciones). El orden es Raw → dbt → Spark porque la OBT se construye desde GOLD | `kestra/ingesta.yml`, `kestra/ingesta/cargar_dia.py`, `docker-compose.yml` (`ENV_PROYECTO_DIR`), `README.md` (fase 1), `docs/ingesta_ejecuciones.csv` | **Aplicado.** Ejecución `1MthBaBVmK0HcOrWcp8Uo0` (2026-11-27): las 4 tareas en `SUCCESS` en 32 min 28 s. `cargar_raw` 731/731 fechas y 1.852.394 filas (29 min 55 s, `forzar=true`); `dbt_build` PASS=75 (20 s); `spark_obt` OBT de 1.852.394 filas con sus validaciones (2 min 8 s); `validar_obt` 5.000/5.000 (4 s). La OBT reconstruida tiene la **misma huella** que la referencia y el snapshot del PSet 3 (sección 3) |
| 3 | Calificación perfecta | Sin correcciones. Solo se actualizan las decisiones que cambian (sección 2) | — | — |

**Lo que se conserva del PSet 2 (y sigue siendo demostrable):**
- **Backfill:**
  - con el rango como input (ejecución `1MthBaBV…`);
  - con el backfill nativo del trigger diario (Triggers → Backfill) y el input `transformar=false`, para que cada día solo cargue RAW: ejecuciones `2FWXIAKX…`, `tCuPU6uE…` y `5newV8VO…` (2019-01-04 a 2019-01-06), una por día y en `SUCCESS`.
- **Reintentos:**
  - por día, con 3 intentos y espera creciente, visibles en el log: la ejecución `23i6JtWI…` con `simular_falla_dia=2019-01-02` muestra `2019-01-02: intento 1 falló (...); reintento en 5 s` y después el día completo;
  - de la tarea, con `retry` exponencial de 3 intentos (`simular_falla=true`).
- **Idempotencia:** cada día se borra y se inserta en una transacción. Con `forzar=false` se omiten los días ya completos.

**Qué cambió frente al PSet 2:**
- Las transformaciones (dbt y Spark) se ejecutan **dentro del mismo flujo** y no a mano.
- La carga agrupa el rango en una tarea con concurrencia interna, en lugar de una ejecución por día: así dbt y Spark corren una sola vez al final.

## 2. Decisiones de PSet anteriores que cambian

| Decisión original | Cambio | Motivo | Dónde | Estado |
|---|---|---|---|---|
| PSet 3: un solo umbral (alertar o no, 0,2400) | Dos umbrales, para las tres acciones del PSet 1: **aprobar** < 0,2400 ≤ **verificar** < u₂ ≤ **retener**. u₂ es el puntaje donde la precisión llega a ≥ 90 % en las predicciones fuera de pliegue (OOF) de la CV del champion, nunca en la prueba | La decisión del PSet 1 tiene tres caminos; la cola del analista (retener) debe tener sobre todo fraudes | `scripts/umbral_retener.py`, `docs/api/umbral_retener.json`, tag `umbral_retener` de la versión 1 en MLflow, `api/main.py` | **Aplicado.** u₂ = **0,8493** (precisión 90,0 % en las predicciones OOF de la CV, 995.049 filas de validación en 389 días). Por día, en promedio (p95): verificar **7,9** (15) y retener **13,8** (31). Retener captura el 91,5 % de los fraudes OOF; verificar, el 5,7 %. u₁ se reprodujo exacto: 0,23999331 |
| PSet 3: notebooks 01–05 ejecutados con Restart + Run All | En `proyecto_final/notebooks/` se copian **con su salida guardada** y **no se vuelven a ejecutar** | El 03 y el 05 borran y recrean sus corridas en MLflow, registran versiones y mueven los aliases: volver a ejecutarlos cambiaría el `run_id` y la versión del champion. Restart + Run All aplica a los notebooks nuevos (06 y 07) | `notebooks/`, `README.md` | Aplicado |
| PSet 3: alerta de desempeño contra la media y desviación de la CV (0,961 ± 0,016) | El umbral se calibra con la **distribución semanal** de la AUC-PR fuera de pliegue (OOF) del entrenamiento | La desviación de la CV se midió en pliegues de ~330 mil filas; un lote semanal (~20 mil filas, ~77 fraudes) varía mucho más y la alerta daría falsas alarmas | `monitoreo/`, `docs/` | Pendiente (fase 4) |
| PSet 2 y 3: cuenta de Snowflake del PSet 2 | Se mantiene la **cuenta original** (la prueba vence después de la entrega del 28-nov). Se crea el esquema `PRODUCCION` para la simulación. La cuenta nueva queda como **respaldo**, con `snowflake/01_setup.sql` | Continuidad: misma OBT con la que se entrenó el champion | `snowflake/02_produccion.sql`, `snowflake/01_setup.sql`, `README.md` | Aplicado |
| PSet 1: las reglas fijas aprueban o rechazan | En **modo de respaldo** de la API, una alerta de las reglas se traduce en **verificar** (OTP o "¿reconoce esta compra?") y no en retener o rechazar | Las reglas alertan al ~30 % de las legítimas (PSet 3, prueba): mandarlas al analista colapsaría la cola. Verificar con el cliente es reversible y barato | `api/main.py` | Aplicado |
| PSet 3: `docs/corridas.csv` completo | `docs/predicciones.csv` es una **muestra trazable** (todos los fraudes, todas las alertas y el 1 % de las legítimas) más `docs/predicciones_por_lote.csv`. La tabla completa queda en Snowflake (`PRODUCCION.PREDICCIONES`) y en un Parquet fuera de git | La tabla completa (~525 mil filas) supera el límite de 100 MB por archivo de GitHub | `docs/`, `README.md` | Pendiente (fase 7) |

## 3. Verificación de equivalencia de la OBT

Antes de reconstruir nada, se guardó la huella de la OBT de la cuenta original y del snapshot del PSet 3, que coinciden (`docs/obt_huella_referencia.json`):

| | Valor |
|---|---|
| Filas / fraudes | 1.852.394 / 9.651 |
| SHA-256 de contenido (ordenado por `trans_num`, decimales redondeados a 6) | `0af7a5e9487e73e25d0e9f57906dad38abf69a750fff32edc38b602a7f797a9b` |
| `HASH_AGG` en Snowflake | `4472567123843243718` |

La OBT reconstruida con la ingesta corregida (fase 1) se compara contra estos valores con `scripts/huella_obt.py`.
