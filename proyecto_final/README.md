# Proyecto final · Centinela: detección de fraude con tarjeta, de punta a punta

> **Estado: en construcción (fase 1 de 8 terminada).** Este README se completa al final con el orden de ejecución completo desde cero.

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

## Snowflake

- **Cuenta en uso:** la original del PSet 2, con las mismas credenciales por par de llaves (`.env` y `secrets/snowflake_key.p8`, fuera de git). El esquema `PRODUCCION` del PSet 4 se crea una vez como ACCOUNTADMIN con [`snowflake/02_produccion.sql`](snowflake/02_produccion.sql).
- **Alternativa (cuenta nueva de respaldo):** si la cuenta original no está disponible, ejecuta [`snowflake/01_setup.sql`](snowflake/01_setup.sql) en la cuenta nueva (crea el warehouse, el resource monitor, los esquemas `RAW`…`OBT` y `PRODUCCION`, el rol y el usuario de servicio), genera un par de llaves nuevo y apunta `SNOWFLAKE_ACCOUNT` en `.env` a esa cuenta. Después reconstruye la OBT con la ingesta (fase 1) y verifica su equivalencia con `scripts/huella_obt.py` (referencia en `docs/obt_huella_referencia.json`).

## Documentación

- [`docs/cambios.md`](docs/cambios.md): observaciones de los PSet 1 a 3 y decisiones que cambian.
- `docs/datos/`: evidencia del pipeline de datos (PSet 2). `docs/eda/`, `docs/features/`, `docs/modelos/`, `docs/tuning/` y `docs/seleccion/`: evidencia de la experimentación (PSet 3).
- `docs/historial/`: memos de los PSet anteriores.
