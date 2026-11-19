# Decisiones y limitaciones del experimento (PSet 3)

Todas las cifras salen de ejecuciones reales. Están en los notebooks, en los CSV de esta carpeta y en MLflow (`docs/corridas.csv`).

## Datos

| Elemento | Valor |
|---|---|
| Tabla de origen | `CENTINELA.OBT.TRANSACCIONES_OBT` (PSet 2) |
| Snapshot | `pset_3/data/obt_snapshot.parquet` (fuera de git). Corte: `2026-11-18 14:52:45.511 -0800` (hora de Snowflake). SHA-256 `9be410f73fb8c090e7647fc27559665c28431d29a0652548d16d8b932d9e9bce` |
| Filas | 1.852.394 (40 columnas); 0,521 % de fraude |
| Entrenamiento | ene-2019 a jun-2020: **1.326.733 filas, 0,576 % de fraude** |
| Prueba (hold-out) | jul-dic 2020: **525.661 filas, 0,383 % de fraude**. Usada una sola vez, en el notebook 05 |

## Decisión 1: CV temporal con ajuste submuestreado y validación a prevalencia real

**Qué se hizo** (`CVTemporalSubmuestreada` en `src/pipeline.py`):
- `TimeSeriesSplit(n_splits=3)` sobre el entrenamiento, ordenado por `trans_ts`.
- En cada pliegue, el bloque de **ajuste** conserva **todos los fraudes y el 5 % de las legítimas**, con una semilla fija por pliegue.
- El bloque de **validación** queda **completo**, con su prevalencia real.

| Pliegue | Filas de ajuste (fraudes) | Filas de validación (fraudes) | Ajuste hasta | Validación desde |
|---|---|---|---|---|
| 0 | 18.829 (2.363) | 331.683 (1.535) | 2019-06-07 03:47 | 2019-06-07 03:59 |
| 1 | 36.871 (3.898) | 331.683 (1.772) | 2019-10-09 19:54 | 2019-10-09 20:27 |
| 2 | 55.139 (5.670) | 331.683 (1.969) | 2020-02-10 18:45 | 2020-02-10 18:55 |

**Por qué:**
- **Temporal:** el modelo predice transacciones futuras, y las ventanas de comportamiento dependen del orden en el tiempo. Una CV aleatoria mezclaría futuro y pasado.
- **No por grupo:** el banco puntúa a sus propios tarjetahabientes, que ya tienen historial. Separar por cliente simularía clientes nuevos, que no es el caso de uso.
- **Submuestreo solo en el ajuste:** hace que el experimento quepa en el presupuesto de cómputo del Codespace (4 núcleos, 16 GB). Con los modelos por defecto, cada CV completa de 3 pliegues tardó: regresión logística ~5 s, RandomForest ~10 s, HistGB ~21 s, MLP ~56 s. Así, los 5 candidatos y las 90 configuraciones del tuning entran en ~1,5 h.
- **Validación a prevalencia real:** como no se submuestrea la validación, la AUC-PR y la pérdida neta de la CV son comparables con la prueba. Si se validara con datos submuestreados, la AUC-PR saldría inflada, porque crece con la prevalencia.
- **AUC-PR de entrenamiento ponderada:** en el bloque de ajuste se calcula con peso 1/0,05 para cada legítima, lo que la lleva a la prevalencia real. Así la **brecha** entrenamiento − CV mide sobreajuste y no la diferencia de prevalencia (~10 % en el ajuste frente a ~0,5 % en validación).
- **Modelo final:** se ajusta con la misma estrategia sobre todo el entrenamiento (todos los fraudes y el 5 % de las legítimas) y se evalúa con **todas** las filas de la prueba.

**Limitación:**
- Cada modelo ve solo ~5 % de las legítimas: unas 64.000 de 1,32 M en el ajuste final. Puede perder patrones raros de comportamiento legítimo. No se midió la sensibilidad a la fracción (por ejemplo, 10 % o 20 %) por falta de tiempo.
- Las probabilidades no están **calibradas** a la prevalencia real: el modelo aprendió con ~10 % de fraudes. Por eso el umbral no se fija en 0,5, sino que se elige con las predicciones fuera de pliegue, que sí tienen la prevalencia real.
- Los modelos de cada pliegue se entrenan con menos datos que el modelo final, así que la distribución de puntajes puede cambiar un poco. El umbral elegido en la CV puede no ser exactamente el óptimo del modelo final.

## Decisión 2: métricas

- **Técnica: AUC-PR** (`average_precision`), la misma para todos los modelos. La exactitud se descarta: con 0,576 % de fraude, un modelo que dice "nunca es fraude" acierta el 99,4 %. El Dummy da AUC-PR 0,005 en CV, que equivale a la prevalencia.
- **De negocio: pérdida neta** = monto del fraude no detectado + USD 5 por falsa alarma (supuesto del PSet 1). El umbral se elige **minimizando esa pérdida con las predicciones fuera de pliegue** de la CV y después se aplica, sin cambios, a la prueba.
- **Simplificación:** el PSet 1 proponía dos umbrales (aprobar, verificar o retener). Aquí se usa **uno**, el de alertar o no. El segundo umbral queda para el PSet 4, cuando se defina la capacidad del equipo de fraude.

## Decisión 3: features y columnas excluidas

- **Derivadas finales:**
  - `log_amt` (de la EDA);
  - `amt_sobre_p95_categoria` (de la EDA; el p95 se aprende solo en el ajuste);
  - `log_segundos_desde_anterior`.

  La hora cíclica se descartó porque no mejoró en ningún modelo (ablación pareada en `docs/features/`).
- **Excluidas** (`pipeline.EXCLUIDAS`): identificadores, fechas y partición, `source_file` (delata el archivo de Kaggle), coordenadas crudas, `comercio` (693 valores) y `job` (497), `franja` (redundante) y **`gender`** (atributo sensible, excluido por equidad).

## Decisión 4: líneas base

- **Ingenua:** `DummyClassifier(strategy="prior")`. AUC-PR en CV 0,0053 ± 0,0005; pérdida neta fuera de pliegue USD 2.842.810.
- **De negocio:** las reglas fijas del PSet 1. AUC-PR en CV 0,0123 ± 0,0014; pérdida neta fuera de pliegue USD 1.661.011.
- **Supuesto:** el PSet 1 decía "compra nocturna sobre un monto mínimo" sin fijar el valor. Se usó **USD 100**.

## Decisión 5: LLM por prompting

- **Modelo:** `gemini-3.5-flash-lite`, en la capa gratuita de Google AI Studio.
  - `gemini-2.5-flash` devolvió 404 ("no longer available to new users").
  - `gemini-3.8-flash` devolvió 503 por alta demanda, y `gemini-flash-latest`, 504.
- **Planteamiento:** 8 ejemplos few-shot del bloque de ajuste del último pliegue. Evaluación sobre **120 transacciones** (24 fraudes) del bloque de validación de ese mismo pliegue, en lotes de 24. Fueron 5 solicitudes y 31.167 tokens en 43 s.
- **Resultado sobre la misma muestra:** AUC-PR 0,962 para Gemini; 0,998 para HistGB y RandomForest; 0,989 para MLP; 0,916 para la regresión logística y 0,332 para las reglas.

**Limitaciones:**
- La muestra es muy pequeña y tiene **20 % de prevalencia**, no la real. La cifra no es comparable con la AUC-PR de la CV.
- El LLM no pasa por la misma CV que los demás, y no es viable en producción: latencia de segundos por lote, costo por token, límite de solicitudes y datos que salen del banco.
- El modelo disponible depende de la capa gratuita de Google y cambia con el tiempo.

## Decisión 6: tuning

- **Búsqueda aleatoria** (`ParameterSampler`, igual que `RandomizedSearchCV`), con 30 configuraciones por modelo y la misma CV. La tasa de aprendizaje y la regularización se exploran en escala logarítmica. Los espacios de búsqueda están en `docs/tuning/espacios_de_busqueda.json`.
- Cada configuración es una **corrida hija** con parámetros, datos y métricas. El **pipeline entrenado** se guarda solo en la corrida padre, para la mejor configuración, para no guardar 90 modelos que no se usan.
- **Resultados** (`docs/tuning/resumen_tuning.csv`, 90 corridas hijas y 3 padre):

| Modelo | Por defecto (AUC-PR CV) | Mejor de 30 | Mejora | Desviación de referencia | ¿Cuenta? | Brecha por defecto → tuneada | Minutos |
|---|---|---|---|---|---|---|---|
| HistGB | 0,9612 ± 0,0163 | 0,9637 ± 0,0151 | +0,0025 | 0,0163 | No | 0,0368 → 0,0346 | 18,9 |
| RandomForest | 0,9406 ± 0,0202 | 0,9394 ± 0,0189 | −0,0013 | 0,0202 | No | 0,0594 → 0,0457 | 15,4 |
| MLP | 0,9177 ± 0,0233 | 0,9284 ± 0,0255 | +0,0107 | 0,0255 | No | 0,0823 → 0,0549 | 21,6 |

- **Hallazgo:** **ninguna mejora en AUC-PR supera la desviación entre pliegues**. Las versiones por defecto ya estaban cerca del techo en estos datos simulados. Donde el tuning sí ayudó fue en **reducir el sobreajuste**: la brecha bajó 0,014 en RandomForest y 0,027 en MLP.
- **Ejecución:** la primera corrida del tuning se cortó a las 18:48, cuando se cerró el Codespace (en `random_forest_cfg10`). Esas 43 corridas se marcaron como fallidas o se borraron, y el notebook se relanzó completo. `corridas.csv` solo incluye la ejecución completa.

## Decisión 7: versión de cada modelo que compite

**Regla** (sección 1 de `05_seleccion.ipynb`):
1. Si la mejora del tuning supera la desviación entre pliegues, compite la versión tuneada.
2. Si no, las dos empatan en AUC-PR y compite la de **menor brecha**, siempre que las brechas difieran en ≥ 0,01.
3. Si las brechas difieren menos, compite la **de por defecto**, por simplicidad.

| Modelo | Versión elegida | Motivo |
|---|---|---|
| HistGB | **por defecto** | Empate en AUC-PR (+0,0025 ≤ 0,0163) y brechas parecidas (diferencia 0,0021 < 0,01) |
| RandomForest | **tuneada** | Empate en AUC-PR (−0,0013 ≤ 0,0202); menor brecha (0,0457 frente a 0,0594) |
| MLP | **tuneada** | Empate en AUC-PR (+0,0107 ≤ 0,0255); menor brecha (0,0549 frente a 0,0823) |

## Decisión 8: selección del ganador y evaluación en prueba

- **Ganador frente al segundo en CV:** HistGB (por defecto) con 0,9612 ± 0,0163, frente a RandomForest (tuneado) con 0,9394 ± 0,0189.
  - La diferencia es **0,0219**, mayor que la desviación entre pliegues (0,0189).
  - HistGB gana en los **3 de 3** pliegues (diferencias pareadas de +0,025, +0,023 y +0,017).
  - **El ganador se decide por AUC-PR**, sin necesidad de desempate.
- **Umbral elegido en la CV** (predicciones OOF, minimizando la pérdida neta): **0,2400** para HistGB y **0,4438** para RandomForest.
- **Prueba (jul-dic 2020, 525.661 filas, 2.012 fraudes)**, evaluada una sola vez en las corridas `fase=final`:

| | AUC-PR | Pérdida neta | Fraude no detectado | Falsas alarmas | Recall | Precisión | % legítimas alertadas | Frente a reglas |
|---|---|---|---|---|---|---|---|---|
| **HistGB (champion)** | **0,9655** | **USD 14.649** | USD 7.134 | 1.503 | 97,4 % | 56,6 % | 0,29 % | **−98,1 %** |
| RandomForest (challenger) | 0,9404 | USD 17.834 | USD 10.424 | 1.482 | 95,4 % | 56,4 % | 0,28 % | −97,7 % |
| Reglas fijas (PSet 1) | 0,0095 | USD 779.426 | USD 6.381 | 154.609 | 83,0 % | 1,1 % | 29,5 % | — |
| Aprobar todo | 0,0038 | USD 1.060.050 | USD 1.060.050 | 0 | 0 % | — | 0 % | +36,0 % |

- **Metas del PSet 1:**
  - pérdida neta al menos 30 % menor que las reglas: **cumplida** (−98,1 %);
  - como máximo 1 % de legítimas enviadas a verificación: **cumplida** (0,29 %).

  El champion genera **18,8 alertas por día**, frente a 849,3 de las reglas, en 184 días de prueba. Las reglas dejan escapar menos dinero en fraude (USD 6.381), pero a cambio de 154.609 falsas alarmas.
- **Costo:**
  - HistGB entrena en 3,4 s (ajuste final) y puntúa las 525.661 filas en 7,2 s (13,8 ms por 1.000 transacciones);
  - RandomForest tarda 39,1 s en entrenar y 3,6 s en puntuar.

  Los dos alcanzan de sobra para un proceso por lotes. En una autorización en línea se puntúa una transacción a la vez.
- **Explicabilidad** (importancia por permutación en una muestra de prueba): `amt` (caída de AUC-PR de 0,69), `categoria` (0,41), `gasto_24h` (0,07) y `es_nocturna` (0,02) son las variables con más peso en los dos modelos. Coincide con los hallazgos de la EDA: monto alto para su categoría, ráfaga de gasto y compra nocturna.
- **Registro:** `centinela-modelo` **versión 1 = `@champion`** (HistGB, `run_id 70bfd857902b4cc188d52a94d934c442`) y **versión 2 = `@challenger`** (RandomForest, `run_id 24f82ec738f8412c9de7599f4e0051a2`). Las dos versiones salen de sus corridas `fase=final`.
- **Reproducción:** `06_reproduccion.ipynb` carga `models:/centinela-modelo@champion` y obtiene AUC-PR 0,96547 y pérdida neta USD 14.649,03, **idénticas (`==`)** a las registradas: `REPRODUCIDO: True`.

## Otras limitaciones

- **Datos simulados (Sparkov):** los modelos de árboles llegan a AUC-PR ~0,96 en CV sin ajustar hiperparámetros. El fraude simulado parece más fácil de separar que el real, así que las métricas son una **cota superior** de lo que se lograría con datos de un banco.
- **Cambio de prevalencia:** el fraude baja de 0,576 % en entrenamiento a 0,383 % en prueba. El umbral elegido en la CV puede no ser el óptimo en la prueba.
- **Sobreajuste visible** en RandomForest y MLP por defecto: AUC-PR de entrenamiento de 1,000 y brechas de +0,059 y +0,082. El tuning las redujo a +0,046 y +0,055.
- **Un solo umbral:** el modelo alerta o no alerta. Los dos umbrales del PSet 1 (aprobar, verificar o retener) y la capacidad diaria del equipo de fraude quedan para el PSet 4.
- **Interrupciones del Codespace:** se cerró dos veces, a las 18:48 (durante el tuning) y después del commit del 04. El tuning se relanzó completo. Los volúmenes de MLflow conservaron todas las corridas terminadas.
