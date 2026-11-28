# Incidentes de la simulación de producción (fase 4)

Registro de lo que falló, cómo se resolvió y qué quedó corregido. Horas en UTC del 2026-11-27.

## 1. Pausa 1 (paso 12): la decisión no se pudo escribir en `PRODUCCION.REENTRENAMIENTOS`

**Qué pasó**

1. En el paso 12 se disparó el reentrenamiento por calendario. `entrenar` terminó bien: challenger v3, evaluado en el
   lote 10; pérdida por 1.000 de 16,20 (champion v1) frente a 18,30 (challenger), mejora −2,10 frente a 4,51. La regla
   recomendó **rechazar**.
2. La ejecución `6Flrm4ebd62EISjnBWTvad` de `reentrenamiento` se detuvo en la pausa. Se reanudó en la interfaz de
   Kestra con `aprobar = false` y el motivo «La mejora en pérdida por 1000 (-2,10) no supera 4,51; se rechaza según la regla».
3. La tarea `decidir` aplicó la decisión en MLflow (etiqueta `decision = rechazada` en la versión 3 y en su corrida;
   el alias `champion` siguió en la v1). Al escribir la decisión en Snowflake, falló en sus 2 intentos con:
   `DML operation to table PRODUCCION.REENTRENAMIENTOS failed on column MOTIVO_DECISION with error: Numeric value '…' is not recognized`.
4. **Causa:** la tabla se había creado sola con `write_pandas(auto_create_table=True)` a partir de la primera fila, en
   la que `MOTIVO_DECISION` estaba vacía. Snowflake la tipó como `NUMBER`.
5. Por `transmitFailed`, quedaron en `FAILED` la ejecución de `reentrenamiento`, el monitoreo del paso 12
   (`4grPFs2JJNClEPlUWu5dme`, en su tarea `disparo`) y la simulación principal (`7ST9UOarLtEZD4i1u2liB9`, pasos 0 a 12).

**Cómo se resolvió**

- Como la columna estaba vacía (1 fila, 0 valores), se eliminó y se volvió a agregar como `VARCHAR`. No se perdió ningún dato.
- La API de Kestra no permitió reiniciar la ejecución fallida (`POST /executions/6Flrm4ebd62EISjnBWTvad/restart`
  respondió 404 «Requested Flow is not found»). Por eso la decisión se registró **fuera de Kestra**, con el **mismo
  código** (`python src/reentrenar.py decidir --paso 12 --aprobar false --motivo "…"`), en la misma imagen
  `centinela-ml:1.0` y con la respuesta exacta de la pausa. Resultado: `PRODUCCION.REENTRENAMIENTOS`, paso 12,
  recomendación `rechazar`, decisión `rechazada`, con el motivo, a las 04:27:32. Coincide con la regla.
- La simulación se relanzó desde el paso 13 (`7RYaimmmy9MPEIKxM531D1`). Los pasos 0 a 12 ya estaban completos y cada
  paso es idempotente.
- El monitoreo del paso 12 no se volvió a ejecutar: su tarea `monitorear` había terminado en `SUCCESS` antes del
  subflujo de reentrenamiento, y `PRODUCCION.MONITOREO` tiene sus 107 métricas (77 de datos, 12 de desempeño, 9 de
  modelo y 9 de sistema, igual que los demás pasos) y `PRODUCCION.ALERTAS`, sus 4 alertas.

**Corrección:** commit `49a5a12`. `src/reentrenar.py` crea `PRODUCCION.REENTRENAMIENTOS` con tipos explícitos
(`DDL_REENTRENAMIENTOS`) antes de escribir. Las pausas 2 a 4 se completaron íntegras dentro de Kestra (`entrenar` → `aviso` → `aprobacion` → `decidir`, todas en `SUCCESS`): ejecuciones `31u65UU6JNDTgGNaTuSIkZ` (paso 17), `3wgThCLoWCtOUjqBB7ePbD` (paso 21) y `25gX96ugw8BStmSTB3WNc2` (paso 25).

## 2. Construcción de la fase 4: la limpieza del paso borró predicciones de prueba de la fase 2 (restauradas)

**Qué pasó:** en el primer ensayo del paso 0 (desde el Codespace, antes de la simulación), la limpieza que hace
idempotente el paso (`DELETE … WHERE LOTE = 0`) borró **200** de las 204 predicciones de prueba de la fase 2, que
debían conservarse, más su solicitud en `SOLICITUDES`. Esas 200 venían de una prueba de `/predecir_lote` con
`lote = 0` (01:05 UTC), y se había supuesto, sin verificarlo, que todas tenían `LOTE` nulo.

**Cómo se resolvió:** se restauraron **idénticas** con Time Travel de Snowflake
(`INSERT … SELECT … BEFORE(STATEMENT => <id del DELETE>)`). Quedan las 204: 200 con `LOTE = 0` y 4 con `LOTE` nulo, todas de las 01:05 UTC.

**Corrección:** la tabla `PRODUCCION.SIMULACION` guarda el instante de inicio de la simulación vigente. Todo borrado,
lectura y monitoreo de la simulación se limita a `LOTE IS NOT NULL AND TS_UTC >= inicio` (`FILTRO_SIM` en
`src/produccion.py`). Las predicciones anteriores al inicio no se pueden tocar.

## 3. La cuenta original de Snowflake quedó suspendida (27 de noviembre): paso a la cuenta de respaldo

**Qué pasó:** terminó la prueba gratuita de la cuenta original. La conexión con el par de llaves y
las consultas de metadatos seguían respondiendo (por ejemplo, `COUNT(*)` de la OBT: 1.852.394), pero toda consulta
que necesita el warehouse fallaba con:
`000666 (57014): Your account is suspended due to lack of payment method.`
Sin cómputo no funcionan la ingesta, la escritura de predicciones de la API, `demo_deriva.sh` ni `demo_reentrenamiento.sh`.
El tablero siguió funcionando con los CSV de `docs/` (su modo de respaldo), y el rollback y el respaldo de la API no
dependen de Snowflake.

**Cómo se resolvió (2026-11-28), con la cuenta de respaldo prevista desde el inicio del PSet 4:**
1. Configuración: `snowflake/01_setup.sql` ejecutado como ACCOUNTADMIN con la **misma llave pública** (no se generaron
   llaves nuevas). En `.env` solo cambió `SNOWFLAKE_ACCOUNT`; se regeneró `.env.kestra` y se recrearon `kestra`, `api` y `tablero`.
   Verificación: usuario `CENTINELA_SVC`, rol `CENTINELA_ROLE`, warehouse `CENTINELA_WH`, cómputo funcionando.
2. Ingesta completa en Kestra (`ingesta.yml`, 2019-01-01 a 2020-12-31, `forzar=true`): ejecución `7JHYWGCoTIpIuRQdUX2gpr`, `SUCCESS` en 8 min 14 s (`cargar_raw` 731/731 fechas y 1.852.394 filas en 5 min 23 s; `dbt_build` PASS=75; `spark_obt` 2 min 17 s; `validar_obt` 5.000/5.000). La OBT reconstruida es **idéntica** a la de referencia: SHA-256 de contenido `0af7a5e9…7a9b`, `HASH_AGG` 4472567123843243718, 1.852.394 filas y 9.651 fraudes (`scripts/huella_obt.py`).
3. Lotes de la simulación (`simulacion/construir_lotes.py`, desde el snapshot local): idénticos a los de la cuenta
   original, con 338.152 filas en `LOTES` y `docs/simulacion/lotes.csv` sin ningún cambio.
4. Atajo para las demostraciones (`simulacion/cargar_targets_llegados.py`): el target de los lotes 0 a 23 se copió a
   `TARGETS_LLEGADOS` (308.056 filas, 1.956 fraudes, las mismas cifras de la simulación) sin volver a correr los 26 pasos.
5. Comprobaciones: el ensayo del reentrenamiento de demostración (`--ensayo`, sin escribir nada) da lo mismo que en la
   cuenta original (v5 230,99 frente a challenger 191,35 por 1.000; +39,64 → promover). Una predicción de prueba
   (`/predecir`, `LOTE` nulo) quedó registrada en `PRODUCCION.PREDICCIONES` sin errores.

**Qué no se trasladó:** las tablas de la simulación completa (`PREDICCIONES`, `SOLICITUDES`, `MONITOREO`, `ALERTAS` y
`REENTRENAMIENTOS`) quedaron en la cuenta suspendida. Sus resultados están exportados en `docs/` (`monitoreo.csv`,
`alertas.csv`, `reentrenamientos.csv`, `predicciones.csv`, `simulacion/*.csv`) y el tablero los muestra en modo CSV. La
simulación se puede repetir en la cuenta nueva con `bash scripts/simular_produccion.sh 0 25` (~27 min más las pausas).
El registro de modelos (MLflow) es local y no se vio afectado: champion v5.
