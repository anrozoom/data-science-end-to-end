# Calidad de datos (diagnóstico sobre RAW, antes de transformar)

**Fuente analizada:** `CENTINELA.RAW.TRANSACCIONES`, cargada por Kestra con el backfill completo 2019-2020: **1.852.394 filas** (`fraudTrain.csv` 1.296.675 + `fraudTest.csv` 555.719), todas como texto.

**Cómo se obtuvieron las cifras:** [`scripts/diagnostico_calidad.py`](../scripts/diagnostico_calidad.py) corre 19 consultas SQL sobre RAW y escribe los resultados, con el SQL exacto de cada uno, en [`calidad_resultados.md`](calidad_resultados.md). La ejecución sobre los datos completos fue el 2026-11-16 a las 01:14 UTC. Una corrida previa sobre datos parciales (1,19 M filas, a mitad del backfill) mostró los mismos patrones, y con esos resultados se diseñó la capa SILVER antes de que terminara la carga.

```bash
# desde pset_2/
docker compose run --rm -v ./scripts:/scripts:ro -v ./docs:/docs --entrypoint python dbt /scripts/diagnostico_calidad.py
```

## Resultados por dimensión

| Dimensión | Revisión | Resultado |
|---|---|---|
| **Volumen** | Filas por archivo | 1.296.675 (train) + 555.719 (test) = **1.852.394**, igual a la fuente |
| | Cobertura de fechas | 2019-01-01 a 2020-12-31: **730 de 731 días** con datos; falta **2020-02-29** |
| | Tasa de fraude | **0,521 %** (9.651 fraudes) en total; **0,579 %** en train y **0,386 %** en test |
| **Completitud** | Nulos o vacíos en las 23 columnas | **0** en todas |
| **Precisión** | `trans_num` duplicado | **0** (1.852.394 distintos) |
| | Filas idénticas en todas las columnas de negocio | **0** |
| | Índice original (columna sin nombre) | Solo 1.296.675 valores distintos: el índice **se reinicia en `fraudTest.csv`**, así que **555.719 filas (30,00 %)** repiten un índice de train |
| | Días presentes en los dos archivos | Ninguno: train y test no se solapan |
| **Consistencia** | Fechas como texto | 0 filas sin parsear en `trans_date_trans_time`, `dob` o `unix_time` |
| | `unix_time` frente a `trans_date_trans_time` | Diferencia constante de **−2.556 a −2.557 días** (unos 7 años) en el 100 % de las filas |
| | Prefijo `fraud_` en `merchant` | **100 %** de las filas (693 comercios) |
| | Atributos del cliente por `cc_num` | 999 clientes; **0** cambian de nombre, fecha de nacimiento, dirección, coordenadas u ocupación |
| | Atributos del comercio | 693 comercios; **7** con más de una categoría; **693 de 693** con ubicación distinta en cada transacción (2.673 ubicaciones promedio por comercio) |
| | Categóricas | 14 categorías; `gender` ∈ {F, M}; 51 estados; 497 ocupaciones |
| **Validez** | `amt` | 0 no numéricos, **0 ≤ 0**; mínimo 1,00, mediana 47,45, máximo 28.948,90; 46 montos > 10.000 |
| | Coordenadas | **0** fuera de rango (cliente y comercio) |
| | Edad en la fecha de la transacción | De **13 a 96** años; **21.847 filas (1,18 %)** de titulares menores de 18 |
| | Fechas y target | 0 fuera de 2019-2020; `is_fraud` solo toma 0 y 1 |
| | `zip` | **116.389 filas (6,28 %)** con menos de 5 dígitos |
| | `cc_num` | Numérico, de 11 a 19 dígitos |

## Problemas principales y decisiones

| Problema | Evidencia | Acción (dónde) | Justificación |
|---|---|---|---|
| Prefijo artificial en el comercio | El 100 % de `merchant` empieza con `fraud_` (693 comercios) | Quitar el prefijo: `regexp_replace(merchant, '^fraud_', '')` (SILVER). Test `silver_merchant_sin_prefijo_fraud` | Es un artefacto del generador Sparkov, no un dato. Además el nombre sugiere fraude en **todas** las filas, incluidas las legítimas: confunde a quien consulta la tabla |
| `unix_time` inconsistente con la fecha | Desfase constante de −2.556/−2.557 días frente a `trans_date_trans_time` en el 100 % de las filas | Usar `trans_date_trans_time` como tiempo del evento y recalcular la época (`trans_epoch`) a partir de ella. `unix_time` queda en BRONZE solo para trazabilidad (SILVER) | Las ventanas de comportamiento (última hora, 24 h) dependen del tiempo exacto. Mezclar dos relojes desfasados 7 años rompería el orden temporal y la separación train/prueba |
| Código postal sin ceros a la izquierda | 116.389 filas (6,28 %) con `zip` de menos de 5 dígitos | `lpad(zip, 5, '0')` (SILVER). Test `silver_zip_cinco_digitos` | Los códigos de EE. UU. tienen 5 dígitos. La exportación los trató como números y perdió los ceros iniciales. Se tratan como texto para que no se vuelvan a perder |
| Titulares menores de edad | 21.847 filas (1,18 %) con edad de 13 a 17 en la fecha de la transacción | Conservar y marcar con `es_menor_de_edad` en el hecho (GOLD). El test de rango de edad es 10–100 y no 18–100 | En datos simulados no hay forma de saber si es un error. Eliminarlas borraría fraudes etiquetados y sesgaría la tasa. Existen tarjetas adicionales para menores. El modelo podrá usar el indicador |
| Índice original repetido | El índice sin nombre se reinicia en `fraudTest.csv`: 555.719 filas (30 %) repiten un índice de train | No usarlo como clave. Se conserva como `indice_origen`; la clave es `trans_num` (unique y not_null desde SILVER) | El índice es un residuo de `pandas.to_csv`, no un identificador. `trans_num` es único en las 1.852.394 filas |
| Día sin transacciones | 2020-02-29 no aparece en la fuente (730 de 731 días) | Mantener el calendario completo en `dim_fecha` (731 días), sin inventar filas. El flow carga 0 filas ese día y termina bien | Es un hueco del generador (no simula el 29 de febrero), no una falla de la ingesta. Se documenta en las limitaciones |
| Comercios con varias categorías | 7 de 693 comercios aparecen con más de una categoría | La categoría va en su propia dimensión (`dim_categoria`), referenciada desde el hecho; `dim_comercio` lleva `es_multicategoria` | Si la categoría fuera un atributo del comercio, habría que elegir una y se perdería información de 7 comercios |
| Ubicación del comercio distinta en cada transacción | 693 de 693 comercios cambian `merch_lat/long` en cada fila | `merch_lat` y `merch_long` quedan en el hecho; con ellas se calcula `distancia_km` (haversine) en SILVER | No es un atributo estable del comercio; ponerlo en la dimensión colapsaría millones de ubicaciones en una |
| Cambio en la tasa de fraude entre períodos | 0,579 % en train frente a 0,386 % en test | Ninguna en la limpieza. Se documenta para el modelado (PSet 3) | No es un error de datos: es una diferencia real entre períodos y un aviso de deriva para la validación temporal |
| Duplicados y reglas de validez | 0 `trans_num` duplicados; 0 montos ≤ 0; 0 coordenadas inválidas; 0 fechas sin parsear | Se implementan igual: deduplicación por `trans_num` (se queda la carga más reciente) y filtros de validez en SILVER, con tests que comparan conteos | Hoy no eliminan filas (SILVER = 1.852.394), pero protegen las cargas futuras: si un reintento duplicara un día o llegara un monto negativo, la capa limpia no lo dejaría pasar |

## Dónde quedan implementadas

- Limpieza: [`dbt/models/silver/slv_transacciones.sql`](../dbt/models/silver/slv_transacciones.sql)
- Tipos sin reglas de negocio: [`dbt/models/bronze/brz_transacciones.sql`](../dbt/models/bronze/brz_transacciones.sql)
- Tests de estas reglas: ver [`modelo_dimensional.md`](modelo_dimensional.md)
