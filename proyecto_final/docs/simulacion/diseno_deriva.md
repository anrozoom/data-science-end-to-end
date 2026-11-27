# Simulación de producción y deriva inducida

Diseño aprobado el 2026-11-27. Código: `simulacion/construir_lotes.py` (lotes y deriva), `src/produccion.py`
(constantes), `monitoreo/` (umbrales, deriva y alertas), `src/reentrenar.py`. Cifras de esta página:
`docs/simulacion/lotes.csv` y `docs/monitoreo/umbrales.json` (generados por esos scripts).

## 1. Lotes

- Fuente: la partición de **prueba** (jul-dic 2020) del snapshot de la OBT (SHA-256 `9be410f7…`, equivalente
  verificado a `CENTINELA.OBT.TRANSACCIONES_OBT`). Ningún dato de prueba se usó para entrenar ni para elegir umbrales.
- **26 lotes semanales** de 7 días desde el miércoles 2020-07-01; el lote 25 junta los últimos 9 días (23 al 31 de dic.).
- **Horizonte del target: 2 lotes.** La confirmación del fraude (disputa del cliente) llega 2 pasos después: en el
  paso *k* llega el target del lote *k − 2*. Los lotes 24 y 25 nunca reciben target dentro de la simulación.
- **Artefacto del dataset:** Sparkov no tiene ningún fraude después del 2020-12-22 23:13. El lote 25 tiene 0 fraudes
  (su AUC-PR no está definida y, además, su target no llega dentro de la simulación).
- En Snowflake (`CENTINELA.PRODUCCION`): `LOTES` (las 21 entradas del modelo tal como las recibe la API, más las
  marcas y los valores originales de lo alterado), `TARGETS` (target y paso en que llega), `TARGETS_LLEGADOS`
  (lo copia cada paso), `LOTES_RESUMEN` y `SIMULACION` (instante de inicio de la simulación vigente).

## 2. Deriva inducida: dos derivas separadas

Se alteran filas **reales**; no se fabrica ninguna. Semilla del lote *k* = 1000 + *k* (primero D1, luego D2).

| | **D1: deriva de datos (cambia P(x))** | **D2: deriva conceptual (cambia P(y\|x))** |
|---|---|---|
| Desde | lote 10 (2020-09-09) hasta el final | lote 14 (2020-10-07) hasta el final |
| Historia | cierre del comercio presencial | fraude «camuflado»: monto típico y de día |
| Qué se altera | cada legítima de las 10 categorías presenciales (`gas_transport`, `grocery_pos`, `home`, `shopping_pos`, `kids_pets`, `entertainment`, `food_dining`, `personal_care`, `health_fitness`, `misc_pos`) se conserva con probabilidad 0,30. **Se conservan todos los fraudes** | cada fraude del lote, con probabilidad 0,50: `amt` ← un monto legítimo de su misma categoría tomado al azar del **entrenamiento**; `hora` ← entero al azar de 9 a 17; `es_nocturna` ← `False`; `monto_relativo` ← `amt / monto_medio_previo` |
| Qué no se toca | — | `is_fraud`, categoría, distancia y las variables de ráfaga (`n_tx_*`, `gasto_*`, `segundos_desde_anterior`) |
| Trazabilidad | las filas quitadas no existen para la API; su número queda en `LOTES_RESUMEN` | `ALTERADA_D2`, `AMT_ORIGINAL`, `HORA_ORIGINAL`, `MONTO_RELATIVO_ORIGINAL` en `LOTES` |

**Limitación de D2:** el historial de las transacciones *posteriores* del mismo cliente no se recalcula (por ejemplo,
el `gasto_24h` de la compra siguiente conserva el monto original).

**D1 sube la prevalencia.** Al quitar legítimas y conservar todos los fraudes, la prevalencia de los lotes 10 a 13 pasa
de 0,334–0,755 % a 0,761–1,733 %. La AUC-PR depende de la prevalencia (con más
fraudes, la precisión de cada corte sube), así que **parte de que la AUC-PR no caiga, o incluso suba, en los lotes 10 a 13
se explica por la prevalencia y no por un mejor modelo**. Por eso la alerta de desempeño se lee junto con la prevalencia
de cada lote, que se reporta abajo y en el monitoreo.

| Lote | Desde | Hasta | Filas originales | Fraudes | Prevalencia original | Legítimas quitadas (D1) | Fraudes camuflados (D2) | Filas servidas | Prevalencia servida | Target llega en el paso |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2020-07-01 | 2020-07-07 | 20.050 | 66 | 0,329 % | — | — | 20.050 | 0,329 % | 2 |
| 1 | 2020-07-08 | 2020-07-14 | 19.925 | 79 | 0,397 % | — | — | 19.925 | 0,397 % | 3 |
| 2 | 2020-07-15 | 2020-07-21 | 19.926 | 90 | 0,452 % | — | — | 19.926 | 0,452 % | 4 |
| 3 | 2020-07-22 | 2020-07-28 | 19.789 | 62 | 0,313 % | — | — | 19.789 | 0,313 % | 5 |
| 4 | 2020-07-29 | 2020-08-04 | 19.840 | 93 | 0,469 % | — | — | 19.840 | 0,469 % | 6 |
| 5 | 2020-08-05 | 2020-08-11 | 19.902 | 131 | 0,658 % | — | — | 19.902 | 0,658 % | 7 |
| 6 | 2020-08-12 | 2020-08-18 | 19.473 | 63 | 0,324 % | — | — | 19.473 | 0,324 % | 8 |
| 7 | 2020-08-19 | 2020-08-25 | 19.803 | 97 | 0,490 % | — | — | 19.803 | 0,490 % | 9 |
| 8 | 2020-08-26 | 2020-09-01 | 19.740 | 68 | 0,344 % | — | — | 19.740 | 0,344 % | 10 |
| 9 | 2020-09-02 | 2020-09-08 | 16.074 | 101 | 0,628 % | — | — | 16.074 | 0,628 % | 11 |
| 10 | 2020-09-09 | 2020-09-15 | 16.303 | 56 | 0,344 % | 9.174 | — | 7.129 | 0,785 % | 12 |
| 11 | 2020-09-16 | 2020-09-22 | 15.868 | 53 | 0,334 % | 8.908 | — | 6.960 | 0,761 % | 13 |
| 12 | 2020-09-23 | 2020-09-29 | 15.939 | 109 | 0,684 % | 9.015 | — | 6.924 | 1,574 % | 14 |
| 13 | 2020-09-30 | 2020-10-06 | 16.028 | 121 | 0,755 % | 9.046 | — | 6.982 | 1,733 % | 15 |
| 14 | 2020-10-07 | 2020-10-13 | 15.911 | 69 | 0,434 % | 9.022 | 35 | 6.889 | 1,002 % | 16 |
| 15 | 2020-10-14 | 2020-10-20 | 16.018 | 103 | 0,643 % | 9.071 | 39 | 6.947 | 1,483 % | 17 |
| 16 | 2020-10-21 | 2020-10-27 | 15.965 | 76 | 0,476 % | 9.017 | 42 | 6.948 | 1,094 % | 18 |
| 17 | 2020-10-28 | 2020-11-03 | 15.928 | 51 | 0,320 % | 8.964 | 25 | 6.964 | 0,732 % | 19 |
| 18 | 2020-11-04 | 2020-11-10 | 16.126 | 80 | 0,496 % | 9.062 | 32 | 7.064 | 1,133 % | 20 |
| 19 | 2020-11-11 | 2020-11-17 | 15.862 | 42 | 0,265 % | 8.971 | 24 | 6.891 | 0,610 % | 21 |
| 20 | 2020-11-18 | 2020-11-24 | 15.658 | 67 | 0,428 % | 8.963 | 38 | 6.695 | 1,001 % | 22 |
| 21 | 2020-11-25 | 2020-12-01 | 22.199 | 88 | 0,396 % | 12.555 | 47 | 9.644 | 0,912 % | 23 |
| 22 | 2020-12-02 | 2020-12-08 | 31.792 | 100 | 0,315 % | 18.076 | 40 | 13.716 | 0,729 % | 24 |
| 23 | 2020-12-09 | 2020-12-15 | 31.709 | 91 | 0,287 % | 17.928 | 40 | 13.781 | 0,660 % | 25 |
| 24 | 2020-12-16 | 2020-12-22 | 31.921 | 56 | 0,175 % | 18.222 | 27 | 13.699 | 0,409 % | 26 (fuera de la simulación) |
| 25 | 2020-12-23 | 2020-12-31 | 37.912 | 0 | 0,000 % | 21.515 | 0 | 16.397 | 0,000 % | 27 (fuera de la simulación) |

## 3. Umbral de la alerta de desempeño: la CV del PSet 3 llevada a escala semanal

El PDF pide comparar el desempeño de cada lote con la media y la desviación de la CV. Se usa **la misma CV del champion
del PSet 3** (HistGradientBoosting por defecto, `TimeSeriesSplit(3)`, semilla 42), con sus predicciones fuera de pliegue
(OOF) **agrupadas por semana** dentro de cada pliegue de validación, con los mismos cortes de 7 días que los lotes
(`monitoreo/calibrar_umbrales.py`, `docs/monitoreo/semanas_oof.csv`). Las AUC-PR de pliegue se reprodujeron
(0,9386, 0,9691, 0,9760).

| | Umbral por pliegue (descartado) | **Umbral semanal (elegido)** |
|---|---|---|
| Regla | media − 2 desv. de las 3 AUC-PR de pliegue (PSet 3: 0,961 ± 0,016) | media − 2 desv. de las 54 AUC-PR OOF semanales de la misma CV (0,9626 ± 0,0273) |
| Valor | 0,9290 | **0,9081** |
| Semanas OOF de la CV por debajo | 8 de 54 | 2 de 54 (ningún par consecutivo: 0) |
| Lotes de prueba **sin alterar** por debajo (verificación a posteriori) | **2: lotes 0 y 14** (falsas alarmas) | 0 |

**Por qué se descartó el umbral por pliegue:** cada pliegue de validación tiene unas 330.000 filas, y una semana de
la CV unas 17.800 (de 10.178 a 31.612) con 36 a 174 fraudes. La desviación entre 3 pliegues mide la variación de AUC-PR sobre muestras enormes y
subestima el ruido de un lote semanal. Con ese umbral, la propia CV habría estado «en alerta» en
8 de sus 54 semanas, y en la prueba sin alterar habría dado 2 falsas alarmas (lotes 0 y 14).
Las falsas alarmas en la prueba se calcularon *después* de elegir el umbral con la CV y no influyeron en él.

AUC-PR del champion v1 en los lotes de prueba **sin alterar** (`docs/monitoreo/falsas_alarmas_umbral.csv`):

| Lote | AUC-PR | < umbral por pliegue | < umbral semanal |
|---|---|---|---|
| 0 | 0,9271 | **sí** | no |
| 1 | 0,9354 | no | no |
| 2 | 0,9823 | no | no |
| 3 | 0,9565 | no | no |
| 4 | 0,9713 | no | no |
| 5 | 0,9688 | no | no |
| 6 | 0,9535 | no | no |
| 7 | 0,9782 | no | no |
| 8 | 0,9784 | no | no |
| 9 | 0,9741 | no | no |
| 10 | 0,9677 | no | no |
| 11 | 0,9650 | no | no |
| 12 | 0,9755 | no | no |
| 13 | 0,9836 | no | no |
| 14 | 0,9283 | **sí** | no |
| 15 | 0,9816 | no | no |
| 16 | 0,9941 | no | no |
| 17 | 0,9663 | no | no |
| 18 | 0,9425 | no | no |
| 19 | 0,9839 | no | no |
| 20 | 0,9849 | no | no |
| 21 | 0,9847 | no | no |
| 22 | 0,9604 | no | no |
| 23 | 0,9383 | no | no |
| 24 | 0,9673 | no | no |

**Regla de disparo por desempeño:** los **2 lotes etiquetados más recientes**, servidos por el champion **vigente** y
posteriores al último lote usado en una decisión, tienen AUC-PR < 0,9081. Un solo lote bajo el umbral
es una alerta alta (`MOD-DES-1`), pero no reentrena.

## 4. Deriva de datos (PSI)

- Referencia: la **misma semana de 2019** (364 días antes, mismos días de la semana) del entrenamiento, para no
  confundir la temporada de diciembre con deriva.
- Umbrales: < 0,10 estable; de 0,10 a 0,25 aviso (`DAT-PSI-AVISO`, informativa); ≥ 0,25 alerta (`DAT-PSI`, media).
  La deriva de datos sola **no** reentrena.
- Excluidas del PSI, con la evidencia del PSI natural en los 26 lotes **sin alterar** (`docs/monitoreo/psi_natural.csv`):
  - `n_tx_previas` (PSI natural máximo 6,925): contador acumulado del historial del cliente: crece por construcción con el tiempo, así que su PSI contra cualquier referencia pasada es alto aunque la población no cambie.
  - `dia_semana` (PSI natural máximo 0,361): en un lote de 7 días cada día aparece una vez; su PSI solo mide cómo se reparte el volumen entre los días (semanas de feriados), algo que ya vigila la alerta de volumen.
  - `es_fin_de_semana` (PSI natural máximo 0,282): se deriva de dia_semana (sábado o domingo) y hereda el mismo problema: mide el reparto del volumen dentro de la semana, no un cambio de la población.
- Con las exclusiones, el PSI natural máximo de las variables vigiladas es 0,132 (`monto_medio_previo`,
  aviso informativo): ningún lote sin alterar llega a 0,25.
- Kolmogorov-Smirnov (numéricas) y chi-cuadrado (categóricas): se reportan como complemento del diagnóstico. Con
  7.000 a 37.000 filas por lote casi cualquier diferencia es significativa, así que no disparan alertas.

## 5. Otras bandas calibradas con la misma CV

- **Tasa de alertas** (verificar + retener) por semana OOF: media 0,869 %, banda (± 3 desv.)
  0,306 % a 1,432 %. En los lotes 0 a 24 sin alterar la tasa queda dentro de la banda.
  El lote 25 sin alterar (0 fraudes, artefacto del dataset) quedaría en 0,301 %, apenas por debajo del mínimo;
  en la simulación ese lote está alterado por D1.
- **Promoción:** desviación (ddof = 1) de la pérdida neta por 1.000 transacciones entre los 3 pliegues
  (39,30, 33,84, 30,35) = **4,51**. Se promueve si la mejora del
  challenger en el último lote etiquetado supera ese valor.

## 6. Reentrenamiento

- Disparos: por desempeño (sección 3) y por calendario en los pasos 12 y 24, salvo que haya habido una decisión en
  los 4 pasos anteriores.
- Ventana: el entrenamiento del PSet 3 más los lotes etiquetados 0..L−1 (L = último lote etiquetado, que se reserva
  para comparar). Los 4 lotes más recientes de la ventana pesan 5 veces más; mismo submuestreo (todos los fraudes
  y el 5 % de las legítimas, semilla 142), mismos hiperparámetros y mismos umbrales del champion; sin tuning.
- Promoción con aprobación humana (tarea `Pause` de `kestra/reentrenamiento.yml`).
