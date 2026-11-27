# Proyecto final · Centinela: detección de fraude con tarjeta, de punta a punta

> **Estado: en construcción (fases 1 a 3 de 8 terminadas; fase 4 construida, simulación pendiente).** Este README se completa al final con el orden de ejecución completo desde cero.

Proyecto **Centinela**: puntuar cada transacción con tarjeta en el momento de la autorización y decidir **aprobar, verificar o retener**, en reemplazo de las reglas fijas del banco.

**Formulación → Pipeline de datos → OBT → Experimentación → Modelo registrado → API → Pruebas y CI/CD → Predicciones registradas → Monitoreo → Alertas → Reentrenamiento → Resultado de negocio → Presentación ejecutiva**

## Origen de cada parte

| Parte | Viene de | Estado en `proyecto_final/` |
|---|---|---|
| Ingesta (Kestra), dbt y Spark | `pset_2/` (tag `pset-02`) | Copiados. La ingesta se corrige en la fase 1 (observación del PSet 2) |
| `src/` y notebooks 01–05 | `pset_3/` (tag `pset-03`) | Copiados **con su salida guardada**; no se vuelven a ejecutar (ver `docs/cambios.md`) |
| Registro de modelos | MLflow del PSet 3 | Mismos volúmenes: `centinela-modelo` v1 `@champion` y v2 `@challenger` |

## Levantar la infraestructura (fase 0)

```bash
cd proyecto_final
cp .env.example .env && chmod 600 .env     # completar valores (ver .env.example)
bash scripts/generar_secretos_kestra.sh     # secretos de Kestra -> .env.kestra
docker compose up -d                        # Kestra :8080 · Spark UI :8081 · MLflow :5055
```

Si el MLflow del PSet 3 está corriendo, detenlo primero (`cd pset_3 && docker compose stop`): usa el mismo puerto y la misma base de datos.

**No uses `docker compose down -v`:** borraría los volúmenes de MLflow, que guardan el registro de modelos y todas las corridas.

## Fase 1 · Ingesta de punta a punta (fuente → RAW → BRONZE → SILVER → GOLD → OBT)

`kestra/ingesta.yml` (`centinela.ingesta.ingesta`) corre **toda la cadena en una sola ejecución, sin pasos manuales**. Así se corrige la observación del PSet 2, donde dbt y Spark se ejecutaban a mano:

| Tarea | Imagen | Qué hace |
|---|---|---|
| `cargar_raw` | `centinela-ingesta:2.0` | Descarga única de Kaggle al volumen `centinela_datos_fuente` y carga idempotente por día a `RAW.TRANSACCIONES` (`PUT` + `COPY` en una transacción), con varias fechas en paralelo |
| `transformaciones` → `dbt_build` | `centinela-dbt:1.11` | `dbt build`: BRONZE → SILVER → GOLD y los 67 tests. Si un test falla, la cadena se detiene antes de la OBT |
| `transformaciones` → `spark_obt` | `apache/spark:3.5.3` | `spark-submit` contra el clúster del compose (red `centinela_red`). Escribe la OBT solo si pasan sus validaciones de joins |
| `transformaciones` → `validar_obt` | `centinela-dbt:1.11` | Recalcula en SQL las ventanas `n_tx_1h` y `n_tx_24h` en 5.000 filas de la OBT |

Antes de la primera ejecución, desde `proyecto_final/`:

```bash
docker build -t centinela-ingesta:2.0 kestra/ingesta
docker compose build dbt
bash kestra/desplegar_flows.sh
```

**Trigger:** `Schedule` diario a las 03:00 UTC. Carga el día del trigger y actualiza GOLD y la OBT. Como la fuente es estática, los días posteriores a 2020 cargan 0 filas.

**Backfill (dos formas):**
1. **Rango como input.** Kestra → Flows → `ingesta` → **Execute**, con `fecha_inicio=2019-01-01`, `fecha_fin=2020-12-31` y `forzar=true` para reescribir. Carga todo en paralelo (`concurrencia`, 8 por defecto) y transforma una sola vez.
2. **Backfill nativo del trigger.** Kestra → Flows → `ingesta` → **Triggers** → `diario` → **Backfill executions**, con el rango de fechas y el input **`transformar=false`**. Cada ejecución del backfill carga **un día** a RAW y no reconstruye GOLD ni la OBT. Al final, una ejecución con `transformar=true` deja todo al día. Con `transformar=true` en el backfill también funciona, pero dbt y Spark correrían en cada día (~3 min por día).

**Reintentos (cómo verlos en el log):**
- **Por día:** cada fecha tiene 3 intentos con espera creciente (5 s, 10 s). Para verlo, ejecuta con `simular_falla_dia=2019-01-02`. El log de `cargar_raw` muestra `2019-01-02: intento 1 falló (...); reintento en 5 s` y después la carga correcta de ese día, mientras los demás días siguen normalmente.
- **De la tarea:** `cargar_raw` tiene `retry` exponencial (3 intentos). Con `forzar=false`, un reintento solo rehace los días que faltan. Para verlo, ejecuta con `simular_falla=true`: falla todo el primer intento y en la pestaña Gantt se ven dos intentos de la tarea.
- `dbt_build` y `spark_obt` tienen 2 intentos para fallas transitorias de Snowflake.
- Si algo agota sus reintentos, el bloque `errors` registra en el log qué tarea falló.

**Una línea `ERRO` en el log de `spark_obt`:** Spark escribe sus `WARN` por stderr y Kestra los muestra como error. No significan que la tarea falló: el estado de la tarea lo dice.

### Demo de la ingesta (para el video, ~4 min)

```bash
bash scripts/demo_ingesta.sh            # por defecto 2020-12-30 a 2020-12-31, forzar=true, transformar=true
```

Imprime el id de la ejecución. En Kestra → Executions → ese id → **Gantt** se ven las 4 tareas pasar a verde. En la ejecución de prueba `6eTq7Tbc21Q2Y81mltsbhh` tardó **3 min 45 s**: `cargar_raw` 21 s, `dbt_build` 38 s, `spark_obt` 2 min 39 s y `validar_obt` 6 s. GOLD y la OBT se reconstruyen desde RAW completo, así que el resultado es el mismo de la reconstrucción total.

## Fase 2 · API de inferencia (patrón online)

**Patrón: online.** La decisión del PSet 1 (aprobar, verificar o retener) se toma **en el momento de la autorización**, en milisegundos. Las transacciones llegan de forma continua: ~2.500 por día en promedio en el dataset. Si la predicción llega tarde, la compra ya se aprobó y el fraude ya ocurrió. Kestra simula el tráfico de producción hacia la API (fase 4).

**Cuándo sería batch:** si la decisión fuera revisar al día siguiente las compras ya aprobadas, por ejemplo para iniciar contracargos o bloquear la tarjeta antes del próximo ciclo. Ahí una predicción de horas de antigüedad no pierde valor.

`api/` (FastAPI, imagen `centinela-api`, puerto **8000**, servicio `api` del compose):

| Endpoint | Qué devuelve |
|---|---|
| `GET /salud` | Estado, si el modelo cargó, si está en respaldo y el estado del registro en Snowflake |
| `GET /modelo` | Nombre, versión, alias, `run_id` y los dos umbrales del modelo en uso |
| `POST /predecir` | Probabilidad, **decisión** (`aprobar` / `verificar` / `retener`), versión, `run_id` e `id_prediccion` |
| `POST /predecir_lote` | Lo mismo para varias transacciones (tráfico simulado). Cada fila queda como una predicción individual con su id |
| `POST /respaldo` | **Interruptor**, protegido con la cabecera `X-Token` (`ADMIN_TOKEN` de `.env`): `{"activo": true}` fuerza las reglas fijas del PSet 1 |
| `POST /recargar` | Protegido: vuelve a resolver el alias en ese momento |
| `GET /metricas` | Solicitudes por código HTTP y latencias p50 y p95 |

- **Modelo:** se carga desde `models:/centinela-modelo@champion`. Un hilo vuelve a resolver el alias cada `RECARGA_SEGUNDOS` (30 s): mover el alias en MLflow cambia el modelo **sin reconstruir la imagen**.
- **Umbrales:** se leen de los tags de la versión, `umbral_decision` = verificar (0,2400) y `umbral_retener` (0,8493).
- **Validación:** Pydantic con los tipos de la firma de MLflow, rangos de validez y categorías vistas en entrenamiento. Una entrada inválida devuelve **422** con un mensaje que dice qué campo falló (ejemplos en `docs/api/ejemplos_422.json`).
- **Respaldo:** si el modelo no carga, o si el interruptor está activo, responde con las reglas fijas e indica `"respaldo": true`.
- **Registro:** cada predicción va a `CENTINELA.PRODUCCION.PREDICCIONES` (id, timestamp, entradas, salida, decisión, versión, `run_id`, respaldo y latencia en ms) y cada solicitud, a `PRODUCCION.SOLICITUDES`. Se escriben en segundo plano y por microlotes, así que no suman latencia a la respuesta. Trazabilidad de punta a punta en `docs/api/trazabilidad_ejemplo.json`.

```bash
docker compose up -d api
curl -s localhost:8000/modelo
curl -s -X POST localhost:8000/predecir -H 'Content-Type: application/json' -d @docs/api/ejemplo_solicitud.json
curl -s -X POST localhost:8000/respaldo -H "X-Token: $(sed -n 's/^ADMIN_TOKEN=//p' .env)" -H 'Content-Type: application/json' -d '{"activo": true}'
```

Ejemplo de respuesta (`docs/api/ejemplo_respuesta.json`): una transacción de fraude real de la prueba devuelve `probabilidad` 0,9815 → `decision: "retener"`, versión 1, `run_id 70bfd857…`.

## Fase 3 · Pruebas y CI/CD

```bash
pip install -r api/requirements.txt pytest==8.3.3 httpx==0.27.2
pytest tests -v            # 16 pasan y 1 xfail esperado (falla conocida del modelo)
```

| Archivo | Qué prueba |
|---|---|
| `tests/test_contrato.py` | Entrada válida → 200 con el esquema esperado. Campo faltante, tipo incorrecto, categoría desconocida, fuera de rango y campo extra → **422** con el campo que falló. La decisión respeta los dos umbrales. El lote devuelve un id por fila |
| `tests/test_modelo.py` | El modelo exportado (`tests/fixtures/modelo_champion`, con `mlflow.sklearn.save_model`) reproduce la **AUC-PR registrada en MLflow** (`ci_muestra_auc_pr` = 0,99778) sobre la muestra fija `tests/fixtures/muestra_prueba.parquet` (todos los fraudes de la prueba + 8.000 legítimas, semilla 42), con tolerancia 1e-9. Es más alta que la de la prueba completa (0,9655) porque la muestra tiene ~20 % de fraude |
| `tests/test_comportamiento.py` | **B2:** en al menos el **95 %** de los perfiles, la misma compra hecha de noche (23:00) no es menos riesgosa que de día (14:00), y en promedio es más riesgosa. **B5:** en al menos el **90 %** de los perfiles, un monto alto para su categoría (1,5× p95) no es menos riesgoso que uno típico (0,5× p95). Los mínimos son una **tolerancia de negocio**: un HistGB no es monótono por construcción, y el 5 % (B2) o 10 % (B5) restante se revisa como excepción. Valores medidos: **B2 97,5 %** y **B5 94,8 %**. **B1, `xfail` estricto:** un monto muy por encima del p95 (5×) no baja la probabilidad. **El modelo no lo cumple**: la decisión empeora en el 22,6 % de los fraudes (ver `docs/hallazgos/monto_fuera_de_soporte.md`) |
| `tests/test_respaldo.py` | Si el modelo no carga, responde con las reglas fijas e indica `respaldo: true`. El interruptor exige token y fuerza el respaldo. Las reglas coinciden con las del PSet 1 |

**Por qué la tolerancia es de 1e-9:** la predicción de HistGradientBoosting es determinista. Entre máquinas solo cambia el redondeo de punto flotante (~1e-15), mientras que un cambio real del modelo mueve la AUC-PR mucho más.

**GitHub Actions** (en la raíz del repo, con una copia idéntica en `proyecto_final/.github/workflows/`):
- `ci.yml`, en cada push y pull request:
  1. verifica que las dos copias de los workflows sean idénticas;
  2. instala las dependencias;
  3. **construye la imagen** de la API;
  4. corre **pytest**;
  5. hace una prueba de humo de la imagen: la arranca con el modelo del fixture y le pide `/salud` y `/predecir`.
- `cd.yml`: cuando `ci` termina **en verde** para un push a **`master`** (la rama por defecto del fork; el enunciado dice `main`), publica la imagen en **GitHub Container Registry** como `ghcr.io/anrozoom/centinela-api:<hash del commit>` y `:latest`. El `docker-compose.yml` usa esa imagen (variable `API_IMAGEN`).
- **El código se despliega solo, pero el modelo no.** Promover un modelo cambia decisiones sobre dinero y clientes reales, así que exige comparar champion y challenger con la regla de promoción y la aprobación de una persona (fase 5). Por eso el modelo vive en MLflow y la imagen lo carga por alias.
- **Qué queda fuera de CI:** Snowflake, Kestra, Spark y el servidor de MLflow (no son accesibles desde GitHub). La API se prueba con el modelo del fixture y sin registro en Snowflake.

## Fase 4 · Simulación de producción, monitoreo y alertas

Diseño completo, con cifras: [docs/simulacion/diseno_deriva.md](docs/simulacion/diseno_deriva.md).

- **Lotes:** la partición de prueba (jul-dic 2020) en 26 lotes semanales; el target de un lote llega 2 pasos después.
- **Deriva inducida:** D1, deriva de datos, desde el lote 10 (cierre del comercio presencial: 70 % menos legítimas
  presenciales; la prevalencia sube). D2, deriva conceptual, desde el lote 14 (la mitad de los fraudes, con un monto típico y de día).
- **Flujos de Kestra** (`centinela.produccion`): `produccion_lotes` recorre los pasos; en cada uno, el lote pasa por la API
  y llega el target del lote *k − 2*. Después llama a `monitoreo`, que calcula las métricas de sistema, modelo, datos
  (PSI, KS y chi-cuadrado) y desempeño, emite las alertas y, si toca, llama a `reentrenamiento`, que se detiene en una **pausa de aprobación**.
- **Umbrales** calibrados solo con la CV del PSet 3 (`monitoreo/calibrar_umbrales.py` → `docs/monitoreo/umbrales.json`).
  Catálogo de alertas con la plantilla métrica | umbral | ventana | severidad | receptor | acción: `monitoreo/alertas.py`.
- **Tablas** en `CENTINELA.PRODUCCION`: `LOTES`, `TARGETS`, `TARGETS_LLEGADOS`, `LOTES_RESUMEN`, `SIMULACION`, `PREDICCIONES`,
  `SOLICITUDES`, `MONITOREO`, `ALERTAS` y `REENTRENAMIENTOS`. Cada paso es idempotente y solo toca filas posteriores al inicio
  de la simulación vigente (las 204 predicciones de prueba de la fase 2 nunca se tocan).

```bash
# una vez (desde proyecto_final/)
python monitoreo/calibrar_umbrales.py           # umbrales (~3 min)
docker compose build ml                         # imagen centinela-ml:1.0 de las tareas
python simulacion/construir_lotes.py            # lotes con la deriva -> PRODUCCION.LOTES/TARGETS
bash scripts/generar_secretos_kestra.sh && docker compose up -d kestra   # incluye ADMIN_TOKEN
bash kestra/desplegar_flows.sh
# simulación (sigue en Kestra aunque se cierre la terminal)
bash scripts/simular_produccion.sh 0 25
bash scripts/esperar_ejecucion.sh <id>          # termina al llegar a una pausa o al final
```

**Aprobar o rechazar una promoción:** en Kestra, abre *Executions* y entra en la ejecución de `reentrenamiento` en
estado `PAUSED`. El log de la tarea `aviso` muestra la recomendación de la regla. Pulsa **Resume**, elige `aprobar`
(true o false), escribe el motivo y confirma. La simulación continúa sola.

## Snowflake

- **Cuenta en uso:** la original del PSet 2, con las mismas credenciales por par de llaves (`.env` y `secrets/snowflake_key.p8`, fuera de git). El esquema `PRODUCCION` del PSet 4 se crea una vez como ACCOUNTADMIN con [`snowflake/02_produccion.sql`](snowflake/02_produccion.sql).
- **Alternativa (cuenta nueva de respaldo):** si la cuenta original no está disponible, ejecuta [`snowflake/01_setup.sql`](snowflake/01_setup.sql) en la cuenta nueva (crea el warehouse, el resource monitor, los esquemas `RAW`…`OBT` y `PRODUCCION`, el rol y el usuario de servicio), genera un par de llaves nuevo y apunta `SNOWFLAKE_ACCOUNT` en `.env` a esa cuenta. Después reconstruye la OBT con la ingesta (fase 1) y verifica su equivalencia con `scripts/huella_obt.py` (referencia en `docs/obt_huella_referencia.json`).

## Documentación

- [`docs/cambios.md`](docs/cambios.md): observaciones de los PSet 1 a 3 y decisiones que cambian.
- `docs/datos/`: evidencia del pipeline de datos (PSet 2). `docs/eda/`, `docs/features/`, `docs/modelos/`, `docs/tuning/` y `docs/seleccion/`: evidencia de la experimentación (PSet 3).
- `docs/historial/`: memos de los PSet anteriores.
