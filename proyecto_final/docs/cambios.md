# Cambios respecto de los PSet 1 a 3

Cada fila indica la observación o decisión, qué se cambió y en qué archivo. Las entregas anteriores quedan intactas en sus carpetas y tags (`pset_2/` con `pset-02`, `pset_3/` con `pset-03`). El proyecto final copia lo necesario a `proyecto_final/`.

## 1. Observaciones del profesor

| PSet | Observación | Qué cambié | Dónde | Estado |
|---|---|---|---|---|
| 1 (9,7) | No se puede repetir el mismo protocolo de validación en el dataset real ULB/Worldline (`mlg-ulb/creditcardfraud`): no tiene las variables de distancia ni el historial del cliente | Se retira la validación externa con ULB del plan. Un contraste con ULB solo sería válido con variables compatibles (monto y hora relativa derivada de `Time`) o con otra fuente real con historial por tarjeta. Queda como limitación | `docs/cambios.md`, `docs/datos/limitaciones.md`, `README.md` (limitaciones) | Aplicado |
| 2 (Kestra 8,5) | "Integra dbt y Spark en el flujo. La ingesta, los reintentos y el backfill funcionan, pero las transformaciones aún se ejecutan manualmente." | `kestra/ingesta.yml` encadena en **una sola ejecución**, sin pasos manuales: carga por día a RAW (subflows concurrentes) → dbt (BRONZE → SILVER → GOLD, con tests) → Spark (OBT con sus validaciones). El orden es Raw → dbt → Spark porque la OBT se construye desde GOLD | `kestra/ingesta.yml`, `kestra/ingesta/cargar_dia.py`, `docker-compose.yml` (`ENV_PROYECTO_DIR`), `README.md` (fase 1), `docs/ingesta_ejecuciones.csv` | **Aplicado.** Ejecución `1MthBaBVmK0HcOrWcp8Uo0` (2026-11-27): las 4 tareas en `SUCCESS` en 32 min 28 s. `cargar_raw` 731/731 fechas y 1.852.394 filas (29 min 55 s, `forzar=true`); `dbt_build` PASS=75 (20 s); `spark_obt` OBT de 1.852.394 filas con sus validaciones (2 min 8 s); `validar_obt` 5.000/5.000 (4 s). La OBT reconstruida tiene la **misma huella** que la referencia y el snapshot del PSet 3 (sección 3) |
| 3 | Calificación perfecta | Sin correcciones. Solo se actualizan las decisiones que cambian (sección 2) | — | — |

Incidentes de la fase 4 (fallo de tipo en `REENTRENAMIENTOS` en la pausa 1; predicciones de prueba borradas y restauradas): [`docs/simulacion/incidentes.md`](simulacion/incidentes.md).

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
| PSet 3: un solo umbral (alertar o no, 0,2400) | Dos umbrales, para las tres acciones del PSet 1: **aprobar** < 0,2400 ≤ **verificar** < u₂ ≤ **retener**. u₂ es el puntaje donde la precisión llega a ≥ 90 % en las predicciones fuera de pliegue (OOF) de la CV del champion, nunca en la prueba | La decisión del PSet 1 tiene tres caminos; la cola del analista (retener) debe tener sobre todo fraudes | `scripts/umbral_retener.py`, `docs/api/umbral_retener.json`, tag `umbral_retener` de la versión 1 en MLflow, `api/main.py` | **Aplicado.** u₂ = **0,8493** (precisión 90,0 % en las predicciones OOF de la CV, 995.049 filas de validación en 389 días). Alertas por día en franjas excluyentes, promedio (p95): **verificar (0,24 a 0,85)** 7,9 (15); **retener (0,85 o más)** 13,8 (31); **total de alertas** 21,7 (42) (`docs/api/alertas_por_dia_franjas.csv`). Retener captura el 91,5 % de los fraudes OOF; verificar, el 5,7 %. u₁ se reprodujo exacto: 0,23999331 |
| PSet 3: notebooks 01–05 ejecutados con Restart + Run All | En `proyecto_final/notebooks/` se copian **con su salida guardada** y **no se vuelven a ejecutar** | El 03 y el 05 borran y recrean sus corridas en MLflow, registran versiones y mueven los aliases: volver a ejecutarlos cambiaría el `run_id` y la versión del champion. Restart + Run All aplica a los notebooks nuevos (06 y 07) | `notebooks/`, `README.md` | Aplicado |
| PSet 3: alerta de desempeño contra la media y desviación de la CV (0,961 ± 0,016) | Se usa **la misma CV del PSet 3 llevada a escala semanal**: la AUC-PR OOF de esa CV agregada en semanas de 7 días dentro de cada pliegue (54 semanas, 0,9626 ± 0,0273). Umbral = media − 2 desv. = **0,9081**; se reentrena con 2 lotes consecutivos del champion vigente por debajo | Un pliegue tiene unas 330.000 filas y una semana unas 17.800: la desviación entre pliegues subestima el ruido de un lote. El umbral por pliegue (0,9290) deja 8 de 54 semanas de la CV por debajo y habría dado **2 falsas alarmas** en la prueba sin alterar (lotes 0 y 14); el semanal deja 2 semanas (nunca 2 seguidas) y ningún lote de prueba | `monitoreo/calibrar_umbrales.py`, `docs/monitoreo/umbrales.json`, `docs/simulacion/diseno_deriva.md` (§3) | Aplicado |
| Plan del PSet 4 (aprobado al inicio): una sola deriva desde el lote ~17 de 26 | **Dos derivas separadas.** D1, deriva de datos, desde el lote 10: se quita el 70 % de las legítimas presenciales y se conservan todos los fraudes, así que la prevalencia sube (lote 10: de 0,343 % a 0,786 %). D2, deriva conceptual, desde el lote 14: la mitad de los fraudes se camufla con un monto legítimo típico de su categoría y en horario diurno | Separar la deriva de datos sin caída de desempeño (no debe reentrenar) de la deriva conceptual (sí). Empezar antes deja 2 ciclos de reentrenamiento y 8 lotes etiquetados después del primero | `simulacion/construir_lotes.py`, `docs/simulacion/diseno_deriva.md`, `docs/simulacion/lotes.csv` (prevalencia por lote) | **Aplicado.** Simulación completa (`docs/simulacion/resultados.md`): D1 sola no disparó reentrenamiento (AUC-PR 0,974 a 0,991 en los lotes 10 a 13) y ningún lote sin alterar dio alertas de severidad media o mayor; D2 disparó 3 reentrenamientos por desempeño (pasos 17, 21 y 25), y el calendario 1 (paso 12). Se promovieron la v4 y la v5; se rechazaron la v3 y la v6 |
| PSet 2 y 3: cuenta de Snowflake del PSet 2 | Hasta el 27-nov se usó la **cuenta original** con el esquema `PRODUCCION`. Ese día **quedó suspendida** al terminar la prueba (`000666: Your account is suspended due to lack of payment method`), y desde el 28-nov se usa la **cuenta de respaldo**, configurada con `snowflake/01_setup.sql` y la misma llave pública | Continuidad: la simulación completa (26 pasos) corrió en la cuenta original y sus resultados están exportados en `docs/`; en la cuenta de respaldo se reconstruyeron la OBT (ingesta completa), los lotes y los targets que necesitan las demostraciones | `snowflake/01_setup.sql`, `.env` (solo `SNOWFLAKE_ACCOUNT`), `simulacion/cargar_targets_llegados.py`, `docs/simulacion/incidentes.md` (§3), `README.md` | Aplicado |
| PSet 1: las reglas fijas aprueban o rechazan | En **modo de respaldo** de la API, una alerta de las reglas se traduce en **verificar** (OTP o "¿reconoce esta compra?") y no en retener o rechazar | Las reglas alertan al ~30 % de las legítimas (PSet 3, prueba): mandarlas al analista colapsaría la cola. Verificar con el cliente es reversible y barato | `api/main.py` | Aplicado |
| PSet 3: `docs/corridas.csv` completo | `docs/predicciones.csv` es una **muestra trazable** (todos los fraudes, todas las alertas y el 1 % de las legítimas) más `docs/predicciones_por_lote.csv`. La tabla completa queda en Snowflake (`PRODUCCION.PREDICCIONES`) y en un Parquet fuera de git | La tabla completa (~525 mil filas) supera el límite de 100 MB por archivo de GitHub | `scripts/exportar_docs.py`, `docs/predicciones.csv`, `docs/predicciones_por_lote.csv`, `README.md` | **Aplicado.** Muestra de 6.398 de 338.152 predicciones (1.956 fraudes, 1.146 alertas y 3.296 del 1 % restante; 5,5 MB) |

## 3. Hallazgos que afectan decisiones anteriores

| Hallazgo | Evidencia | Consecuencia |
|---|---|---|
| **El modelo es más permisivo con montos MUY altos para su categoría** (falla de comportamiento de negocio) | En la muestra fija de prueba (2.012 fraudes), llevar el monto a 5× el p95 de su categoría **baja** la probabilidad en el 90,8 % de los fraudes. La caída típica es pequeña (mediana −0,021, media −0,125), pero la **decisión empeora en el 22,6 %**: retener pasa del 91,6 % al 73,0 % y el 9,3 % quedaría aprobado. Causa en los datos: el fraude más caro del entrenamiento vale USD 1.376 y **ninguna** de las 780 transacciones con monto > 5× p95 es fraude (Sparkov) | No se maquilla: prueba `xfail(strict=True)` (avisa si un modelo futuro lo corrige), hallazgo en `docs/hallazgos/monto_fuera_de_soporte.md` (con curva y tablas), **criterio de retirada** (fase 7) y limitación. Las pruebas de comportamiento que sí cumple: compra nocturna ≥ diurna (medido 97,5 %) y monto 1,5× p95 ≥ 0,5× p95 (medido 94,8 %) |

| **El modelo da más falsas alarmas a las mujeres** (equidad) | En los lotes sin alterar (0 a 9, champion v1), el 0,315 % de las compras legítimas de mujeres recibe una alerta, frente al 0,243 % de las de hombres: 1,30 veces (p = 0,003). En ventanas de 4 lotes, la tasa de las mujeres es la más alta en 20 de 21, y en 8 la diferencia es mayor que 1,25 y significativa. La mezcla de categorías no lo explica (tasas estandarizadas de 0,285 % y 0,279 %). El género no es una entrada del modelo | El criterio de retirada R2 (equidad) se activa: revisión de equidad, con el análisis de las variables que actúan como sustituto del género pendiente. Se documenta en `docs/etica/etica.md` y en las limitaciones |

## 4. Verificación de equivalencia de la OBT

Antes de reconstruir nada, se guardó la huella de la OBT de la cuenta original y del snapshot del PSet 3, que coinciden (`docs/obt_huella_referencia.json`):

| | Valor |
|---|---|
| Filas / fraudes | 1.852.394 / 9.651 |
| SHA-256 de contenido (ordenado por `trans_num`, decimales redondeados a 6) | `0af7a5e9487e73e25d0e9f57906dad38abf69a750fff32edc38b602a7f797a9b` |
| `HASH_AGG` en Snowflake | `4472567123843243718` |

La OBT reconstruida con la ingesta corregida (fase 1) se compara contra estos valores con `scripts/huella_obt.py`.
