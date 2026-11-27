# Resultados del diagnóstico de calidad (RAW)

> Nota del proyecto final: copia de la evidencia del PSet 2 (`pset_2/docs/`, tag `pset-02`). Los enlaces apuntan a los archivos de `proyecto_final/`; `backfill_paralelo.sh` y `flows/ingesta_diaria.yml` se reemplazaron por `kestra/ingesta.yml` en la fase 1 (`docs/cambios.md`) y los enlaces a ellos llevan a su versión original en `pset_2/`.

> Generado automáticamente por `scripts/diagnostico_calidad.py` el 2026-11-16 01:14 UTC sobre **1,852,394 filas** de `CENTINELA.RAW.TRANSACCIONES`. No editar a mano: volver a correr el script.


## Volumen


### Filas totales, por archivo de origen y tasa de fraude

| _source_file | filas | fraudes | pct_fraude |
|---|---|---|---|
| fraudTest.csv | 555,719 | 2,145 | 0.386 |
| fraudTrain.csv | 1,296,675 | 7,506 | 0.579 |
|  | 1,852,394 | 9,651 | 0.521 |

<details><summary>SQL</summary>

```sql
SELECT _SOURCE_FILE, COUNT(*) AS filas,
                SUM(IFF(IS_FRAUD = '1', 1, 0)) AS fraudes,
                ROUND(100 * AVG(IFF(IS_FRAUD = '1', 1, 0)), 3) AS pct_fraude
         FROM RAW.TRANSACCIONES GROUP BY ROLLUP(_SOURCE_FILE) ORDER BY _SOURCE_FILE NULLS LAST
```
</details>


### Cobertura de fechas cargadas (_LOAD_DATE)

| primera | ultima | dias_con_datos | dias_calendario | filas_por_dia_prom |
|---|---|---|---|---|
| 2019-01-01 | 2020-12-31 | 730 | 731 | 2,538 |

<details><summary>SQL</summary>

```sql
SELECT MIN(_LOAD_DATE) AS primera, MAX(_LOAD_DATE) AS ultima,
                COUNT(DISTINCT _LOAD_DATE) AS dias_con_datos,
                DATEDIFF('day', MIN(_LOAD_DATE), MAX(_LOAD_DATE)) + 1 AS dias_calendario,
                ROUND(COUNT(*) / COUNT(DISTINCT _LOAD_DATE), 0) AS filas_por_dia_prom
         FROM RAW.TRANSACCIONES
```
</details>


### Días del calendario 2019-2020 sin ninguna transacción

| dia_sin_datos |
|---|
| 2020-02-29 |

<details><summary>SQL</summary>

```sql
WITH cal AS (SELECT DATEADD('day', SEQ4(), '2019-01-01'::DATE) AS d
                      FROM TABLE(GENERATOR(ROWCOUNT => 731)))
         SELECT d AS dia_sin_datos FROM cal
         WHERE d NOT IN (SELECT DISTINCT _LOAD_DATE FROM RAW.TRANSACCIONES) ORDER BY d
```
</details>


## Completitud


### Nulos o vacíos por columna

| indice_origen | trans_date_trans_time | cc_num | merchant | category | amt | first | last | gender | street | city | state | zip | lat | long | city_pop | job | dob | trans_num | unix_time | merch_lat | merch_long | is_fraud |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

<details><summary>SQL</summary>

```sql
SELECT SUM(IFF(INDICE_ORIGEN IS NULL OR TRIM(INDICE_ORIGEN) = '', 1, 0)) AS INDICE_ORIGEN,
                SUM(IFF(TRANS_DATE_TRANS_TIME IS NULL OR TRIM(TRANS_DATE_TRANS_TIME) = '', 1, 0)) AS TRANS_DATE_TRANS_TIME,
                SUM(IFF(CC_NUM IS NULL OR TRIM(CC_NUM) = '', 1, 0)) AS CC_NUM,
                SUM(IFF(MERCHANT IS NULL OR TRIM(MERCHANT) = '', 1, 0)) AS MERCHANT,
                SUM(IFF(CATEGORY IS NULL OR TRIM(CATEGORY) = '', 1, 0)) AS CATEGORY,
                SUM(IFF(AMT IS NULL OR TRIM(AMT) = '', 1, 0)) AS AMT,
                SUM(IFF(FIRST IS NULL OR TRIM(FIRST) = '', 1, 0)) AS FIRST,
                SUM(IFF(LAST IS NULL OR TRIM(LAST) = '', 1, 0)) AS LAST,
                SUM(IFF(GENDER IS NULL OR TRIM(GENDER) = '', 1, 0)) AS GENDER,
                SUM(IFF(STREET IS NULL OR TRIM(STREET) = '', 1, 0)) AS STREET,
                SUM(IFF(CITY IS NULL OR TRIM(CITY) = '', 1, 0)) AS CITY,
                SUM(IFF(STATE IS NULL OR TRIM(STATE) = '', 1, 0)) AS STATE,
                SUM(IFF(ZIP IS NULL OR TRIM(ZIP) = '', 1, 0)) AS ZIP,
                SUM(IFF(LAT IS NULL OR TRIM(LAT) = '', 1, 0)) AS LAT,
                SUM(IFF(LONG IS NULL OR TRIM(LONG) = '', 1, 0)) AS LONG,
                SUM(IFF(CITY_POP IS NULL OR TRIM(CITY_POP) = '', 1, 0)) AS CITY_POP,
                SUM(IFF(JOB IS NULL OR TRIM(JOB) = '', 1, 0)) AS JOB,
                SUM(IFF(DOB IS NULL OR TRIM(DOB) = '', 1, 0)) AS DOB,
                SUM(IFF(TRANS_NUM IS NULL OR TRIM(TRANS_NUM) = '', 1, 0)) AS TRANS_NUM,
                SUM(IFF(UNIX_TIME IS NULL OR TRIM(UNIX_TIME) = '', 1, 0)) AS UNIX_TIME,
                SUM(IFF(MERCH_LAT IS NULL OR TRIM(MERCH_LAT) = '', 1, 0)) AS MERCH_LAT,
                SUM(IFF(MERCH_LONG IS NULL OR TRIM(MERCH_LONG) = '', 1, 0)) AS MERCH_LONG,
                SUM(IFF(IS_FRAUD IS NULL OR TRIM(IS_FRAUD) = '', 1, 0)) AS IS_FRAUD
         FROM RAW.TRANSACCIONES
```
</details>


## Precisión


### Duplicados por trans_num (clave de la transacción)

| filas | trans_num_distintos | filas_duplicadas |
|---|---|---|
| 1,852,394 | 1,852,394 | 0 |

<details><summary>SQL</summary>

```sql
SELECT COUNT(*) AS filas, COUNT(DISTINCT TRANS_NUM) AS trans_num_distintos,
                COUNT(*) - COUNT(DISTINCT TRANS_NUM) AS filas_duplicadas
         FROM RAW.TRANSACCIONES
```
</details>


### Filas idénticas en todas las columnas de negocio

| filas_identicas_repetidas |
|---|
| 0 |

<details><summary>SQL</summary>

```sql
SELECT COUNT(*) - COUNT(DISTINCT HASH(TRANS_DATE_TRANS_TIME, CC_NUM, MERCHANT, CATEGORY, AMT, FIRST, LAST, GENDER, STREET, CITY, STATE, ZIP, LAT, LONG, CITY_POP, JOB, DOB, TRANS_NUM, UNIX_TIME, MERCH_LAT, MERCH_LONG, IS_FRAUD)) AS filas_identicas_repetidas
         FROM RAW.TRANSACCIONES
```
</details>


### Índice original (columna sin nombre) repetido entre archivos

| filas | indices_distintos | indices_por_archivo |
|---|---|---|
| 1,852,394 | 1,296,675 | 1,852,394 |

<details><summary>SQL</summary>

```sql
SELECT COUNT(*) AS filas, COUNT(DISTINCT INDICE_ORIGEN) AS indices_distintos,
                COUNT(DISTINCT _SOURCE_FILE || '|' || INDICE_ORIGEN) AS indices_por_archivo
         FROM RAW.TRANSACCIONES
```
</details>


### Transacciones del día frontera presentes en ambos archivos

| _load_date | _source_file | filas |
|---|---|---|
| 2020-06-21 | fraudTest.csv | 2,028 |
| 2020-06-21 | fraudTrain.csv | 1,366 |

<details><summary>SQL</summary>

```sql
SELECT _LOAD_DATE, _SOURCE_FILE, COUNT(*) AS filas
         FROM RAW.TRANSACCIONES
         WHERE _LOAD_DATE IN (SELECT _LOAD_DATE FROM RAW.TRANSACCIONES GROUP BY 1 HAVING COUNT(DISTINCT _SOURCE_FILE) > 1)
         GROUP BY 1, 2 ORDER BY 1, 2
```
</details>


## Consistencia


### Formato de fechas (texto en RAW)

| trans_date_no_parseable | dob_no_parseable | unix_time_no_numerico |
|---|---|---|
| 0 | 0 | 0 |

<details><summary>SQL</summary>

```sql
SELECT SUM(IFF(TRY_TO_TIMESTAMP_NTZ(TRANS_DATE_TRANS_TIME, 'YYYY-MM-DD HH24:MI:SS') IS NULL, 1, 0)) AS trans_date_no_parseable,
                SUM(IFF(TRY_TO_DATE(DOB, 'YYYY-MM-DD') IS NULL, 1, 0)) AS dob_no_parseable,
                SUM(IFF(TRY_TO_NUMBER(UNIX_TIME) IS NULL, 1, 0)) AS unix_time_no_numerico
         FROM RAW.TRANSACCIONES
```
</details>


### unix_time frente a trans_date_trans_time (diferencia en días)

| dif_min_dias | dif_max_dias | valores_distintos |
|---|---|---|
| -2,557 | -2,556 | 2 |

<details><summary>SQL</summary>

```sql
SELECT MIN(d) AS dif_min_dias, MAX(d) AS dif_max_dias, COUNT(DISTINCT d) AS valores_distintos
         FROM (SELECT DATEDIFF('day', TRY_TO_TIMESTAMP_NTZ(TRANS_DATE_TRANS_TIME, 'YYYY-MM-DD HH24:MI:SS'), TO_TIMESTAMP_NTZ(TRY_TO_NUMBER(UNIX_TIME))) AS d FROM RAW.TRANSACCIONES)
```
</details>


### Prefijo artificial 'fraud_' en merchant

| con_prefijo | pct_con_prefijo | comercios_distintos |
|---|---|---|
| 1,852,394 | 100.00 | 693 |

<details><summary>SQL</summary>

```sql
SELECT SUM(IFF(STARTSWITH(MERCHANT, 'fraud_'), 1, 0)) AS con_prefijo,
                ROUND(100 * AVG(IFF(STARTSWITH(MERCHANT, 'fraud_'), 1, 0)), 2) AS pct_con_prefijo,
                COUNT(DISTINCT MERCHANT) AS comercios_distintos
         FROM RAW.TRANSACCIONES
```
</details>


### Atributos del cliente estables por cc_num

| clientes | con_varios_nombres | con_varias_dob | con_varias_direcciones | con_varias_lat_long | con_varios_job |
|---|---|---|---|---|---|
| 999 | 0 | 0 | 0 | 0 | 0 |

<details><summary>SQL</summary>

```sql
SELECT COUNT(*) AS clientes,
                SUM(IFF(n_nombre > 1, 1, 0)) AS con_varios_nombres,
                SUM(IFF(n_dob > 1, 1, 0)) AS con_varias_dob,
                SUM(IFF(n_dir > 1, 1, 0)) AS con_varias_direcciones,
                SUM(IFF(n_geo > 1, 1, 0)) AS con_varias_lat_long,
                SUM(IFF(n_job > 1, 1, 0)) AS con_varios_job
         FROM (SELECT CC_NUM,
                      COUNT(DISTINCT FIRST || ' ' || LAST || GENDER) AS n_nombre,
                      COUNT(DISTINCT DOB) AS n_dob,
                      COUNT(DISTINCT STREET || CITY || STATE || ZIP) AS n_dir,
                      COUNT(DISTINCT LAT || ',' || LONG) AS n_geo,
                      COUNT(DISTINCT JOB) AS n_job
               FROM RAW.TRANSACCIONES GROUP BY CC_NUM)
```
</details>


### Atributos del comercio: categoría y ubicación por merchant

| comercios | con_varias_categorias | con_varias_ubicaciones | ubicaciones_prom_por_comercio |
|---|---|---|---|
| 693 | 7 | 693 | 2673.0 |

<details><summary>SQL</summary>

```sql
SELECT COUNT(*) AS comercios,
                SUM(IFF(n_cat > 1, 1, 0)) AS con_varias_categorias,
                SUM(IFF(n_geo > 1, 1, 0)) AS con_varias_ubicaciones,
                ROUND(AVG(n_geo), 1) AS ubicaciones_prom_por_comercio
         FROM (SELECT MERCHANT, COUNT(DISTINCT CATEGORY) AS n_cat,
                      COUNT(DISTINCT MERCH_LAT || ',' || MERCH_LONG) AS n_geo
               FROM RAW.TRANSACCIONES GROUP BY MERCHANT)
```
</details>


### Valores distintos de columnas categóricas

| categorias | generos | valores_gender | estados | ocupaciones | tarjetas |
|---|---|---|---|---|---|
| 14 | 2 | M,F | 51 | 497 | 999 |

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT CATEGORY) AS categorias, COUNT(DISTINCT GENDER) AS generos,
                LISTAGG(DISTINCT GENDER, ',') AS valores_gender,
                COUNT(DISTINCT STATE) AS estados, COUNT(DISTINCT JOB) AS ocupaciones,
                COUNT(DISTINCT CC_NUM) AS tarjetas
         FROM RAW.TRANSACCIONES
```
</details>


## Validez


### Monto (amt)

| no_numerico | menor_o_igual_cero | minimo | maximo | mediana | mayor_a_10000 |
|---|---|---|---|---|---|
| 0 | 0 | 1.00 | 28948.90 | 47.45000 | 46 |

<details><summary>SQL</summary>

```sql
SELECT SUM(IFF(TRY_TO_DECIMAL(AMT, 12, 2) IS NULL, 1, 0)) AS no_numerico,
                SUM(IFF(TRY_TO_DECIMAL(AMT, 12, 2) <= 0, 1, 0)) AS menor_o_igual_cero,
                MIN(TRY_TO_DECIMAL(AMT, 12, 2)) AS minimo, MAX(TRY_TO_DECIMAL(AMT, 12, 2)) AS maximo,
                MEDIAN(TRY_TO_DECIMAL(AMT, 12, 2)) AS mediana,
                SUM(IFF(TRY_TO_DECIMAL(AMT, 12, 2) > 10000, 1, 0)) AS mayor_a_10000
         FROM RAW.TRANSACCIONES
```
</details>


### Coordenadas fuera de rango

| lat_invalida | long_invalida | merch_lat_invalida | merch_long_invalida | lat_min | lat_max | long_min | long_max |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 20.0271 | 66.6933 | -165.6723 | -67.9503 |

<details><summary>SQL</summary>

```sql
SELECT SUM(IFF(TRY_TO_DOUBLE(LAT) NOT BETWEEN -90 AND 90 OR TRY_TO_DOUBLE(LAT) IS NULL, 1, 0)) AS lat_invalida,
                SUM(IFF(TRY_TO_DOUBLE(LONG) NOT BETWEEN -180 AND 180 OR TRY_TO_DOUBLE(LONG) IS NULL, 1, 0)) AS long_invalida,
                SUM(IFF(TRY_TO_DOUBLE(MERCH_LAT) NOT BETWEEN -90 AND 90 OR TRY_TO_DOUBLE(MERCH_LAT) IS NULL, 1, 0)) AS merch_lat_invalida,
                SUM(IFF(TRY_TO_DOUBLE(MERCH_LONG) NOT BETWEEN -180 AND 180 OR TRY_TO_DOUBLE(MERCH_LONG) IS NULL, 1, 0)) AS merch_long_invalida,
                MIN(TRY_TO_DOUBLE(LAT)) AS lat_min, MAX(TRY_TO_DOUBLE(LAT)) AS lat_max,
                MIN(TRY_TO_DOUBLE(LONG)) AS long_min, MAX(TRY_TO_DOUBLE(LONG)) AS long_max
         FROM RAW.TRANSACCIONES
```
</details>


### Edad del titular en la fecha de la transacción

| edad_min | edad_max | menores_de_18 | mayores_de_100 |
|---|---|---|---|
| 13 | 96 | 21,847 | 0 |

<details><summary>SQL</summary>

```sql
SELECT MIN(e) AS edad_min, MAX(e) AS edad_max,
                SUM(IFF(e < 18, 1, 0)) AS menores_de_18, SUM(IFF(e > 100, 1, 0)) AS mayores_de_100
         FROM (SELECT DATEDIFF('year', TRY_TO_DATE(DOB, 'YYYY-MM-DD'), TRY_TO_TIMESTAMP_NTZ(TRANS_DATE_TRANS_TIME, 'YYYY-MM-DD HH24:MI:SS'))
                      - IFF(DATEADD('year', DATEDIFF('year', TRY_TO_DATE(DOB, 'YYYY-MM-DD'), TRY_TO_TIMESTAMP_NTZ(TRANS_DATE_TRANS_TIME, 'YYYY-MM-DD HH24:MI:SS')), TRY_TO_DATE(DOB, 'YYYY-MM-DD')) > TRY_TO_TIMESTAMP_NTZ(TRANS_DATE_TRANS_TIME, 'YYYY-MM-DD HH24:MI:SS')::DATE, 1, 0) AS e
               FROM RAW.TRANSACCIONES)
```
</details>


### Rango de fechas de transacción y valores del target

| primera_transaccion | ultima_transaccion | fuera_de_2019_2020 | is_fraud_invalido |
|---|---|---|---|
| 2019-01-01 00:00:18 | 2020-12-31 23:59:34 | 0 | 0 |

<details><summary>SQL</summary>

```sql
SELECT MIN(TRY_TO_TIMESTAMP_NTZ(TRANS_DATE_TRANS_TIME, 'YYYY-MM-DD HH24:MI:SS')) AS primera_transaccion, MAX(TRY_TO_TIMESTAMP_NTZ(TRANS_DATE_TRANS_TIME, 'YYYY-MM-DD HH24:MI:SS')) AS ultima_transaccion,
                SUM(IFF(TRY_TO_TIMESTAMP_NTZ(TRANS_DATE_TRANS_TIME, 'YYYY-MM-DD HH24:MI:SS') NOT BETWEEN '2019-01-01' AND '2020-12-31 23:59:59', 1, 0)) AS fuera_de_2019_2020,
                SUM(IFF(IS_FRAUD NOT IN ('0', '1') OR IS_FRAUD IS NULL, 1, 0)) AS is_fraud_invalido
         FROM RAW.TRANSACCIONES
```
</details>


### Otros campos: city_pop, zip y cc_num

| city_pop_invalida | zip_no_numerico | zip_menos_de_5_digitos | cc_num_largo_min | cc_num_largo_max | cc_num_no_numerico |
|---|---|---|---|---|---|
| 0 | 0 | 116,389 | 11 | 19 | 0 |

<details><summary>SQL</summary>

```sql
SELECT SUM(IFF(TRY_TO_NUMBER(CITY_POP) IS NULL OR TRY_TO_NUMBER(CITY_POP) <= 0, 1, 0)) AS city_pop_invalida,
                SUM(IFF(NOT REGEXP_LIKE(ZIP, '[0-9]{3,5}'), 1, 0)) AS zip_no_numerico,
                SUM(IFF(LENGTH(ZIP) < 5, 1, 0)) AS zip_menos_de_5_digitos,
                MIN(LENGTH(CC_NUM)) AS cc_num_largo_min, MAX(LENGTH(CC_NUM)) AS cc_num_largo_max,
                SUM(IFF(TRY_TO_NUMBER(CC_NUM) IS NULL, 1, 0)) AS cc_num_no_numerico
         FROM RAW.TRANSACCIONES
```
</details>
