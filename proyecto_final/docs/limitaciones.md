# Limitaciones del proyecto final (problemas no resueltos)

Complementa `docs/datos/limitaciones.md` (pipeline, PSet 2) y `docs/experimentacion/decisiones_y_limitaciones.md`
(experimentación, PSet 3).

## Datos

- **Datos simulados (Sparkov).** Los patrones de fraude son los del generador: por ejemplo, ningún fraude supera USD 1.376
  en el entrenamiento (hallazgo B1) y no hay fraudes después del 2020-12-22 (el lote 25 tiene 0). Las cifras de negocio
  valen para estos datos, no para un banco real.
- **Validación externa con ULB/Worldline descartada** (observación del PSet 1): ese dataset no tiene distancia ni
  historial por cliente. Un contraste solo sería válido con variables compatibles (monto y hora relativa) o con otra fuente real.
- **Costo de una falsa alarma fijo en USD 5** (supuesto del PSet 1). Subestima el costo de retener a un cliente legítimo.

## Simulación y deriva

- **La deriva es inducida y conocida.** D1 y D2 se diseñaron para que el monitoreo las detectara; una deriva real puede
  ser más gradual o mezclada.
- **D2 no recalcula el historial** de las transacciones posteriores del cliente (por ejemplo, `gasto_24h` conserva el monto
  original del fraude camuflado). Eso deja al modelo una señal que en la realidad cambiaría.
- **D1 sube la prevalencia** (se quitan legítimas y se conservan todos los fraudes); la AUC-PR de los lotes 10 a 13 sube en parte por eso.
- **Recuperación parcial:** después de dos reentrenamientos, la v5 queda en una AUC-PR de 0,75 a 0,79, por debajo del umbral
  de 0,9081. El fraude camuflado se parece, por construcción, a una compra legítima. El umbral de alerta no se recalibró
  para los modelos reentrenados, que siguen contrastándose con la CV del champion original.
- **El reentrenamiento no siempre mejora en cada lote:** la v4 perdió más que la v1 en el lote 20.
- Los umbrales de decisión (0,2400 y 0,8493) no se recalibran al reentrenar (sin tuning, según el enunciado).
- **Lotes 24 y 25 sin target** dentro de la simulación (horizonte de 2 lotes).
- **Batch semanal, no streaming:** el patrón de servicio es online (la API responde en milisegundos), pero el monitoreo y
  el reentrenamiento corren por lote semanal y el target llega con 2 semanas de retraso.

## Equidad

- **Más falsas alarmas para las mujeres** (1,30 veces en los lotes sin alterar; criterio R2 activado). No se identificó qué
  variables actúan como sustituto del género: la mezcla de categorías no lo explica. Queda pendiente el análisis de causa y
  la corrección (por ejemplo, un reentrenamiento con restricción de equidad), sin umbrales distintos por grupo.
- Los subgrupos por edad tienen pocas falsas alarmas por lote; el análisis por ventanas de 4 lotes reduce el ruido, pero
  42 pruebas al 5 % dejan unos 2 falsos positivos esperados.

## Arquitectura y operación

- **Todo corre en un Codespace** (4 núcleos, 16 GB): sin alta disponibilidad, una réplica de la API y el backend de MLflow en SQLite.
- **Alertas solo en el log de Kestra** y en `PRODUCCION.ALERTAS`; correo o Slack no se configuraron.
- **Kestra open source:** la API no permitió reiniciar la ejecución fallida de la pausa 1, y la decisión se registró con el
  mismo código fuera de Kestra (`docs/simulacion/incidentes.md`).
- **Las demostraciones del video** (pasos y lotes ≥ 100) escriben en las mismas tablas que la simulación; quedan fuera de
  los resúmenes y exportes, pero la demostración de reentrenamiento crea una versión real en el registro de modelos.
- **Prueba de Snowflake** con vencimiento: hay una cuenta de respaldo documentada (`snowflake/01_setup.sql`).
