# Limitaciones y problemas no resueltos

## Datos

| Limitación | Evidencia | Impacto | Qué haría falta |
|---|---|---|---|
| **Datos simulados** (generador Sparkov) | Nombres, direcciones y comercios sintéticos; el prefijo `fraud_` está en el 100 % de los comercios; `unix_time` desplazado ~7 años | Los patrones de fraude pueden ser más fáciles que los reales: las métricas del modelo serán una **cota superior** | Validar con datos reales de un emisor (piloto shadow pedido en el PSet 1) |
| **ULB/Worldline no entra en el pipeline** | Observación del profesor al PSet 1: ULB no tiene distancia ni historial del cliente (solo `Time`, `Amount` y `V1`–`V28` anonimizadas por PCA) | No se puede repetir el mismo protocolo de validación en datos reales | Cualquier contraste con ULB solo vale con variables compatibles (monto y hora relativa derivada de `Time`), o hace falta otra fuente real con historial por tarjeta |
| **Día faltante en la fuente** | 2020-02-29 no tiene transacciones (730 de 731 días) | Hueco de un día en las ventanas de 24 h que cruzan esa fecha; `dim_fecha` lo conserva como día sin hechos | Ninguna en el pipeline: es una propiedad del generador |
| **Cambio en la tasa de fraude entre archivos** | 0,579 % en `fraudTrain.csv` frente a 0,386 % en `fraudTest.csv` | Deriva del target entre el período de entrenamiento y el de prueba | Tenerlo en cuenta al calibrar umbrales y en la validación temporal (PSet 3) |
| **Titulares menores de edad** | 21.847 filas (1,18 %) de titulares de 13 a 17 años | No se sabe si es un error del generador o tarjetas adicionales | Se conservan con el indicador `es_menor_de_edad`; confirmarlo con el negocio |
| **Etiquetas posiblemente incompletas (MNAR)** | Riesgo identificado en el PSet 1: el fraude no reportado queda etiquetado como 0 | El recall medido puede sobreestimarse | No se puede verificar con este dataset |
| **Atributos del cliente sin historia** | `dim_cliente` es SCD tipo 1. Hoy no hay cambios (test `gold_cliente_sin_cambios_de_atributos`) | Si en el futuro cambiaran la dirección o la ubicación, se perdería el valor anterior | Pasar a SCD tipo 2 (por ejemplo, con snapshots de dbt) si aparecen cambios |

## Arquitectura

| Limitación | Detalle | Qué haría falta |
|---|---|---|
| **El backfill nativo del trigger es secuencial en Kestra 2.0.7** | Medido: ~1 ejecución cada 5,5 s y nunca más de una corriendo, aunque el flow permite 16. 731 días tomarían ~67 min | Para el histórico se usó [`kestra/backfill_paralelo.sh`](../kestra/backfill_paralelo.sh), que crea una ejecución por fecha del mismo flow (8 min 12 s). El backfill nativo queda para recuperar pocos días |
| **La "ingesta diaria" es simulada** | La fuente es un archivo estático. El trigger diario de fechas actuales (2026) termina con 0 filas; el histórico entra por backfill | Con una fuente real, el flow leería el extracto del día anterior en vez de un archivo pre-dividido |
| **Orquestador local** | Kestra corre en el Codespace: cuando el Codespace se apaga, el `Schedule` no dispara. Al volver, `recoverMissedSchedules: NONE` no recupera los días perdidos (se recuperan con backfill) | Desplegar Kestra en un servidor siempre encendido |
| **dbt y Spark no están orquestados por Kestra** | Hoy se ejecutan con `docker compose run --rm dbt build` y `bash spark/ejecutar_obt.sh` después de la ingesta | Agregar al flow tareas que corran dbt y Spark al terminar la carga del día (o un flow aparte que dependa del de ingesta) |
| **OBT completa en cada corrida** | El job reescribe las 1,85 M filas (`overwrite`, ~2 min) | Hacerlo incremental por fecha, recalculando solo las ventanas afectadas (las últimas 24 h) |
| **OCSP en el conector de Spark** | El log del job muestra `Using fail-open`: el driver JDBC no pudo consultar el servidor de revocación de certificados y siguió con TLS normal | En producción, permitir la salida a los servidores OCSP o configurar el caché de OCSP |
| **El job de Spark corre como root en `spark-master`** | Solo para poder leer la llave privada montada con permisos 600 (dueño: el usuario del Codespace) | Montar la llave como secreto de Docker con permisos para el usuario `spark` |
| **Prueba de Snowflake con fecha de vencimiento** | La cuenta de prueba vence alrededor del 2026-11-26 | Toda la evidencia numérica quedó en `docs/`. Con una cuenta nueva basta repetir `snowflake/01_setup.sql` y los comandos del README |
| **Sin PNG del diagrama** | El diagrama de [`arquitectura.md`](arquitectura.md) está en Mermaid | Exportarlo desde <https://mermaid.live> si el documento lo requiere |
