# Ingesta con Kestra: fuente → RAW

## Resumen

| Aspecto | Implementación |
|---|---|
| Fuente | Kaggle `kartik2112/fraud-detection` (Sparkov, CC0): `fraudTrain.csv` y `fraudTest.csv`, descargados con la API de Kaggle (`KAGGLE_API_TOKEN`, paquete `kaggle` 2.2.5) |
| Flow | [`kestra/flows/ingesta_diaria.yml`](../kestra/flows/ingesta_diaria.yml) (`centinela.ingesta.ingesta_diaria`) |
| Imagen de la tarea | [`kestra/ingesta/Dockerfile`](../kestra/ingesta/Dockerfile) → `centinela-ingesta:1.0` (Python 3.11, `snowflake-connector-python` 4.8.0) |
| Script | [`kestra/ingesta/cargar_dia.py`](../kestra/ingesta/cargar_dia.py) |
| Destino | `CENTINELA.RAW.TRANSACCIONES` (todo `VARCHAR` + `_SOURCE_FILE`, `_LOAD_DATE`, `_INGESTED_AT`) |
| Granularidad | **Una ejecución = un día de transacciones** (~2.538 filas por día en promedio) |
| Trigger | `Schedule` diario, `cron: "0 2 * * *"` (02:00 UTC), con `recoverMissedSchedules: NONE` |
| Retries | `exponential`: 10 s inicial, máximo 2 min, **4 intentos** |
| Errores | Bloque `errors` con log `ERROR` que dice qué fecha falló; timeout de 20 min por tarea |
| Concurrencia | `limit: 16`, `behavior: QUEUE` |
| Credenciales | Secretos de Kestra (`{{ secret('...') }}`) desde `.env.kestra`, generado por `scripts/generar_secretos_kestra.sh`; nada en el YAML ni en git |

## Proceso de carga

1. **Descarga única.** La primera ejecución que no encuentra la fuente la baja de Kaggle al volumen Docker `centinela_datos_fuente` y la divide en un archivo por día (`/data/dias/AAAA-MM-DD.csv`), sin limpiar nada. Un candado de archivo (`fcntl`) hace que, si arrancan 16 ejecuciones a la vez, solo una descargue y las demás esperen. Las siguientes ejecuciones reutilizan los archivos.
2. **Carga del día.** `PUT` del archivo del día a un stage interno (`RAW.STG_TRANSACCIONES/<fecha>/`) y `COPY INTO RAW.TRANSACCIONES` dentro de una transacción.
3. **Idempotencia.** Si la fecha ya tenía filas, se borran (`DELETE ... WHERE _LOAD_DATE = fecha`) dentro de la misma transacción antes del `COPY ... FORCE = TRUE`. Un reintento o una re-ejecución reemplaza el día y nunca lo duplica.
4. **Verificación.** Después del `COPY`, compara las filas cargadas con las del archivo; si no coinciden, hace `ROLLBACK` y falla, lo que activa el retry.
5. **Fechas fuera de la fuente.** Para fechas sin archivo (el trigger diario de hoy, en 2026, o el 2020-02-29) registra "Nada que cargar" y termina con éxito.

## Por qué estos parámetros

- **Diario a las 02:00 UTC:** en el escenario real (un banco emisor), las transacciones de un día están completas después de medianoche. La decisión que alimentan los datos (entrenar y monitorear el modelo) no necesita más frecuencia que la diaria (ver la sección de batch frente a streaming del documento).
- **Retry exponencial de 4 intentos:** las fallas esperables son transitorias (la API de Kaggle o la red no responden un momento, Snowflake tarda en encender el warehouse o rechaza una sesión). El backoff exponencial empieza en 10 s y crece hasta un tope de 2 min entre intentos: cubre caídas de alrededor de un minuto sin saturar la fuente con reintentos inmediatos. En la prueba, el intento 1 arrancó ~11 s después del fallo del intento 0 (01:01:33 → 01:01:44 UTC, según los logs): el intervalo inicial de 10 s más el arranque del contenedor. Si la caída durara horas, no se suben los intentos: se re-ejecuta la fecha con backfill, que es seguro por la idempotencia.
- **Concurrencia de 16:** cada día tarda ~6–8 s. Las cargas de días distintos no chocan entre sí (cada una borra solo su `_LOAD_DATE`), y 16 contenedores de 1 GB caben en la máquina de 16 GB.

## Pruebas realizadas (2026-11-16, cifras de Kestra y Snowflake)

| Prueba | Ejecución | Resultado |
|---|---|---|
| Un día (2019-01-01), con descarga y división de la fuente | `6vAsmyLSNLbj8DrcvKBwqF` | `SUCCESS` en 58 s. Logs: `fraudTrain.csv: 1296675 filas`, `fraudTest.csv: 555719 filas`, 730 archivos diarios, 0 filas sin fecha; **2.414 filas cargadas (archivo: 2.414)** |
| Retry + idempotencia (mismo día, `simular_falla = true`) | `1SCl3neqqi8gwhsh41auhz` | Intento 0 `FAILED` (falla simulada) → intento 1 `SUCCESS`: "ya tenía 2414 filas: se reemplazan", **2.414 filas después de la re-ejecución** (no 4.828) |
| Backfill nativo del trigger (2019-01-01 → 2021-01-01) | 26 ejecuciones, etiqueta `tipo=backfill` | Las 26 en `SUCCESS` (2019-01-01 a 2019-01-26). Kestra 2.0.7 las emitió **de a una** (~1 cada 5,5 s, nunca más de una corriendo): el backfill completo habría tomado ~67 min. Se pausó |
| Backfill en paralelo de los días restantes ([`kestra/backfill_paralelo.sh`](../kestra/backfill_paralelo.sh)) | 705 ejecuciones, etiqueta `tipo=backfill-paralelo` | Las 705 en `SUCCESS`, **0 fallidas**, de 01:05:42 a 01:13:54 UTC (**8 min 12 s**) |
| Total en RAW | — | **1.852.394 filas**, 730 días con datos (ver [`calidad_datos.md`](calidad_datos.md)) |

**Decisión sobre el backfill:** el backfill nativo del trigger funciona y queda como mecanismo estándar para recuperar algunos días. Para el histórico completo se usó el mismo flow, con la misma granularidad diaria, lanzando una ejecución por fecha con el input `fecha`. Así se aprovecha la concurrencia del flow: 731 días en ~11 minutos en total.

## Capturas para el documento

1. **Kestra → Flows → `centinela.ingesta.ingesta_diaria` → pestaña Topology** (diagrama del flow con la tarea, el retry y el bloque `errors`).
2. **Ejecución `1SCl3neqqi8gwhsh41auhz` → pestaña Gantt o Logs** (intento 0 en rojo y el intento 1 en verde; abre la tarea `cargar_dia` para ver los dos intentos).
3. **Pestaña Executions del flow, filtrada por la etiqueta `tipo:backfill-paralelo`** (705 en `SUCCESS`).
4. **Pestaña Triggers del flow** (trigger `diario` con el cron y el backfill pausado).
5. **Snowsight:** `SELECT _SOURCE_FILE, COUNT(*) FROM CENTINELA.RAW.TRANSACCIONES GROUP BY 1;`
