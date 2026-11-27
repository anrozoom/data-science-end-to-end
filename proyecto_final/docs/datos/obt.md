# OBT con Spark

> Nota del proyecto final: copia de la evidencia del PSet 2 (`pset_2/docs/`, tag `pset-02`). Los enlaces apuntan a los archivos de `proyecto_final/`; `backfill_paralelo.sh` y `flows/ingesta_diaria.yml` se reemplazaron por `kestra/ingesta.yml` en la fase 1 (`docs/cambios.md`) y los enlaces a ellos llevan a su versión original en `pset_2/`.

## Cómo se construye

- **Job:** [`spark/construir_obt.py`](../../spark/construir_obt.py), lanzado con [`spark/ejecutar_obt.sh`](../../spark/ejecutar_obt.sh).
- **Ejecución:** `spark-submit` dentro de `spark-master` (driver en modo cliente) contra el clúster del compose (1 worker, 2 núcleos, 1.800 MB para el ejecutor).
- **Versiones fijas:** Spark 3.5.3 (imagen oficial `apache/spark:3.5.3-java17-python3`), `spark-snowflake_2.12:3.1.1` (compilado para Spark 3.5) y `snowflake-jdbc:3.19.0` (la versión que declara ese conector).
- **Autenticación:** par de llaves. El conector solo acepta la llave sin cifrar, así que el driver la descifra en memoria con `openssl` (la passphrase va por variable de entorno, no por argumento) y nunca la escribe a disco.

Pasos del job:
1. **Lee de GOLD** `FCT_TRANSACCIONES` y las 5 dimensiones.
2. **Une** el hecho con cada dimensión con `left join` por clave sustituta. Las dimensiones son pequeñas (14 a 999 filas), así que se usa `broadcast`. Con `left join`, una clave sin pareja aparecería como nulo en vez de borrar la transacción, y la validación de nulos lo detectaría.
3. **Calcula variables de comportamiento por cliente** con funciones de ventana sobre `trans_epoch`, que viene de `trans_ts` y no de `unix_time` (ver la limpieza en [`calidad_datos.md`](calidad_datos.md)):

   | Variable | Ventana | Exclusión de la fila actual y del futuro |
   |---|---|---|
   | `n_tx_1h`, `gasto_1h` | `rangeBetween(-3600, -1)` sobre la época en segundos | El límite superior `-1` deja fuera la fila actual (y otras del mismo segundo) y todo lo posterior |
   | `n_tx_24h`, `gasto_24h` | `rangeBetween(-86400, -1)` | Igual |
   | `segundos_desde_anterior` | `lag(t)` ordenado por `(t, trans_num)` | Solo mira la fila anterior |
   | `n_tx_previas`, `monto_medio_previo` | `rowsBetween(unboundedPreceding, -1)` | Solo filas anteriores |
   | `monto_relativo` | `amt / monto_medio_previo` | Nulo en la primera transacción de cada cliente |

4. **Valida** antes de escribir (si un chequeo falla, el job no escribe) y **escribe** `CENTINELA.OBT.TRANSACCIONES_OBT` (`mode overwrite`).
5. **Relee** desde Snowflake el conteo escrito.

## Grano

**Una fila por transacción (`trans_num`)**, el mismo grano que `fct_transacciones` y que la unidad de predicción del PSet 1.

## Columnas (40)

| Grupo | Columnas |
|---|---|
| Identificación y tiempo | `trans_num`, `trans_ts`, `fecha`, `anio`, `mes`, `dia_semana`, `es_fin_de_semana`, `hora`, `es_nocturna`, `franja`, `particion_temporal` |
| Cliente | `cliente_sk`, `gender`, `state`, `city_pop`, `job`, `cliente_lat`, `cliente_long`, `edad_en_transaccion`, `es_menor_de_edad` |
| Comercio y categoría | `comercio_sk`, `comercio`, `es_multicategoria`, `categoria_sk`, `categoria`, `canal` |
| Transacción | `amt`, `merch_lat`, `merch_long`, `distancia_km` |
| Comportamiento (sin fuga) | `n_tx_1h`, `gasto_1h`, `n_tx_24h`, `gasto_24h`, `segundos_desde_anterior`, `n_tx_previas`, `monto_medio_previo`, `monto_relativo` |
| Target y trazabilidad | `is_fraud`, `source_file` |

Se excluyen a propósito el nombre, el apellido, la calle y el `cc_num`: son datos sintéticos e identificadores personales que el PSet 1 decidió no usar como variables.

## Validaciones (ejecución del 2026-11-16 a las 01:20 UTC, 122,8 s)

Resultado completo en [`obt_validaciones.json`](obt_validaciones.json).

| Chequeo | Esperado | Obtenido | ¿Pasa? |
|---|---|---|---|
| `count(OBT) == count(fct_transacciones)` | 1.852.394 | 1.852.394 | ✅ |
| `count(distinct trans_num) == count(OBT)` | 1.852.394 | 1.852.394 | ✅ |
| Tasa de `is_fraud` antes y después de los joins | 0,005210014716 | 0,005210014716 | ✅ |
| Nulos en claves y atributos de dimensiones (10 columnas) | 0 | 0 en todas | ✅ |
| Filas sin transacción anterior = 1 por cliente | 999 | 999 | ✅ |
| Ventanas coherentes (diferencias ≥ 0, `n_tx_1h` ≤ `n_tx_24h`) | 0 incoherentes | 0 | ✅ |
| Filas escritas en Snowflake == `count(OBT)` | 1.852.394 | 1.852.394 | ✅ |

**Validación independiente en SQL** ([`scripts/validar_obt_sql.py`](../../scripts/validar_obt_sql.py), resultado en [`obt_validacion_sql.txt`](obt_validacion_sql.txt)): en una muestra aleatoria de 5.000 transacciones de la OBT, Snowflake recalculó `n_tx_24h` y `n_tx_1h` contando solo las transacciones del mismo cliente en `[t − 86.400, t − 1]` y `[t − 3.600, t − 1]` segundos. **Coinciden 5.000 de 5.000** en las dos variables. Si Spark hubiera incluido la fila actual o filas futuras, los conteos no coincidirían.

## Cuándo usar el star schema y cuándo la OBT en Centinela

| Uso | Estructura | Por qué |
|---|---|---|
| Entrenar y evaluar el modelo (PSet 3), servir variables al puntaje | **OBT** | Una fila por transacción con todas las variables y el target, lista para `pandas`/`scikit-learn` sin joins. Las ventanas por cliente, que son caras, se calculan una sola vez en Spark y no en cada experimento |
| Partición temporal entrenamiento/prueba | **OBT** (`particion_temporal`) | El filtro sale directo de la columna, sin volver a unir con el calendario |
| Análisis y tableros del equipo de fraude (fraude por categoría, por hora, por estado, alertas por día) | **Star schema** | Las métricas se agregan sobre el hecho y se cortan por cualquier dimensión. Un atributo corregido (por ejemplo, el canal de una categoría) se cambia en una sola fila de la dimensión, no en 1,85 M filas |
| Agregar dimensiones o fuentes nuevas (por ejemplo, contracargos o datos reales del banco) | **Star schema** | Es el modelo canónico y gobernado; la OBT se regenera a partir de él |
| Monitoreo de deriva (PSet 4) | Las dos | Las distribuciones de variables se miden sobre la OBT y las tasas por segmento sobre el star schema |

La OBT **no reemplaza** al star schema: es una vista desnormalizada y derivada, que se reconstruye con un solo comando cuando cambia GOLD. El star schema sigue siendo la fuente de verdad.

## Capturas para el documento

1. **UI del master de Spark** (puerto 8081, agrégalo en Ports): en "Completed Applications" aparece `centinela-obt` con el worker y su duración.
2. **Terminal** con el JSON de validaciones que imprime `bash spark/ejecutar_obt.sh`. Para no recalcular, basta con mostrar `docs/datos/obt_validaciones.json`.
3. **Snowsight:** `SELECT * FROM CENTINELA.OBT.TRANSACCIONES_OBT LIMIT 20;` y `SELECT COUNT(*), COUNT(DISTINCT TRANS_NUM) FROM CENTINELA.OBT.TRANSACCIONES_OBT;`
