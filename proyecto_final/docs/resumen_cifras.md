# Resumen de cifras clave · Centinela (PSet 4 / proyecto final)

Para el memo técnico y la presentación ejecutiva. Cada cifra sale de una ejecución real; al lado va el archivo de donde
sale. Fechas en UTC del 2026-11-27.

## Fase 0 · OBT y trazabilidad de datos

| Cifra | Valor | Fuente |
|---|---|---|
| OBT | 1.852.394 filas, 40 columnas, 9.651 fraudes (0,521 %) | `docs/obt_huella_referencia.json` |
| Huella de contenido (SHA-256, ordenada por `trans_num`) | `0af7a5e9…7a9b`: idéntica en la cuenta de Snowflake, en el snapshot del PSet 3 y en la OBT reconstruida en la fase 1 | ídem |
| `HASH_AGG` en Snowflake | 4472567123843243718 | ídem |
| SHA-256 del archivo del snapshot (entrenamiento del champion) | `9be410f7…9bce` | `data/obt_snapshot.json` (fuera de git) |

## Fase 1 · Ingesta de punta a punta (corrección del PSet 2)

| Cifra | Valor | Fuente |
|---|---|---|
| Ejecución completa `1MthBaBVmK0HcOrWcp8Uo0` | 32 min 28 s; `cargar_raw` 731/731 días y 1.852.394 filas (29 min 55 s); `dbt_build` PASS=75 (20 s); `spark_obt` (2 min 8 s); `validar_obt` 5.000/5.000 (4 s) | `docs/cambios.md`, `docs/ingesta_ejecuciones.csv` |
| Demo para el video `6eTq7Tbc21Q2Y81mltsbhh` | 3 min 45 s (21 s, 38 s, 2 min 39 s y 6 s) | `README.md` |
| Reintentos y backfill demostrados | reintento por día `23i6JtWIBoENmnuHwJ56y1`; backfill nativo del trigger (3 ejecuciones) | `docs/ingesta_ejecuciones.csv` |

## PSet 3 (heredado) · Experimentación y selección

| Cifra | Valor | Fuente |
|---|---|---|
| Candidatos (CV AUC-PR, media ± desv.) | regresión logística 0,4960 ± 0,0174; random forest 0,9406 ± 0,0202; **HistGB 0,9612 ± 0,0163**; MLP 0,9177 ± 0,0233; reglas fijas 0,0123; dummy 0,0053 | `docs/modelos/resultados_baseline_candidatos.csv` |
| Tuning (≥ 30 configuraciones por modelo) | HistGB 0,9637 (+0,0025, menos que la desviación: no cuenta); RF 0,9394; MLP 0,9284 | `docs/tuning/resumen_tuning.csv` |
| Champion v1 (HistGB por defecto, run `70bfd857`) en prueba (jul-dic 2020) | AUC-PR **0,9655**; pérdida neta USD 14.649 frente a USD 779.426 de las reglas (−98,1 %); recall 97,4 %; 0,287 % de legítimas alertadas | `docs/seleccion/evaluacion_prueba.csv` |
| Challenger v2 (RF tuneado, run `24f82ec7`) en prueba | AUC-PR 0,9404; pérdida USD 17.834 | ídem |
| Corridas del experimento | 102 en el PSet 3; 106 con los 4 reentrenamientos de la simulación; 108 con las 2 demostraciones del video (v7 y v8) | `docs/corridas.csv` |

## Fase 2 · API de inferencia (patrón online)

| Cifra | Valor | Fuente |
|---|---|---|
| Umbrales | verificar ≥ **0,2400** (costo, PSet 3); retener ≥ **0,8493** (precisión 90,0 % en las predicciones OOF de la CV) | `docs/api/umbral_retener.json` |
| Alertas por día (OOF), promedio (p95) | verificar 7,9 (15); retener 13,8 (31); total 21,7 (42) | `docs/api/alertas_por_dia_franjas.csv` |
| Latencia de `POST /predecir` en la simulación | p50: mediana 10,1 ms por lote; p95 máximo 17,0 ms; 0 respuestas 4xx y 0 5xx | notebook 06, `docs/monitoreo.csv` |
| Respaldo | interruptor: la misma transacción pasa de `retener` (modelo) a `verificar` (reglas); 401 sin token | `docs/demos/respaldo.json` |

## Fase 3 · Pruebas y CI/CD

| Cifra | Valor | Fuente |
|---|---|---|
| Pruebas | 26 en verde y 1 `xfail` (B1): contrato, modelo, comportamiento, respaldo y monitoreo | `tests/` |
| Prueba del modelo | AUC-PR de la muestra fija 0,9977791597765034 (tolerancia 1e-9), registrada en MLflow como `ci_muestra_auc_pr` | `tests/fixtures/metricas_esperadas.json` |
| Comportamiento | B2 (noche ≥ día) se cumple en el 97,5 %; B5 (1,5 × p95 ≥ 0,5 × p95) en el 94,8 % | `tests/test_comportamiento.py` |
| Hallazgo B1 | con 5 × p95 la probabilidad baja en el 90,8 % de los fraudes (mediana −0,021) y la decisión empeora en el 22,6 %; el fraude más caro del entrenamiento es de USD 1.376 | `docs/hallazgos/monto_fuera_de_soporte.md` |

## Fase 4 · Simulación de producción, monitoreo y alertas

| Cifra | Valor | Fuente |
|---|---|---|
| Lotes | 26 semanales; 525.661 transacciones originales (partición de prueba de la OBT); 338.152 servidas a la API después de D1 | `docs/simulacion/lotes.csv` |
| D1 (desde el lote 10) | −70 % de legítimas presenciales; prevalencia del lote 10: de 0,343 % a 0,786 %; PSI de `categoria` de 0,284 a 0,326; volumen de 0,37 a 0,48 del de la misma semana de 2019 | `lotes.csv`, `alertas_por_paso.csv` |
| D2 (desde el lote 14) | 389 fraudes camuflados (lotes 14 a 24): mediana del monto de USD 348,06 a USD 55,53; nocturnos del 84,3 % al 0 % | notebook 06 |
| Umbral de desempeño (CV del PSet 3 a escala semanal) | 54 semanas OOF, 0,9626 ± 0,0273 → **0,9081**. El umbral por pliegue (0,929) dejaba 8 de 54 semanas por debajo y 2 falsas alarmas (lotes 0 y 14 sin alterar); el semanal, 2 semanas y 0 lotes | `docs/monitoreo/umbrales.json`, `docs/simulacion/diseno_deriva.md` |
| PSI natural máximo (variables vigiladas, lotes sin alterar) | 0,132 (`monto_medio_previo`); excluidas: `n_tx_previas` (hasta 6,92), `dia_semana` (0,36), `es_fin_de_semana` (0,28) | `docs/monitoreo/psi_natural.csv` |
| Banda de la tasa de alertas | 0,31 % a 1,43 % (media 0,87 %) | `umbrales.json` |
| **Falsas alarmas en lotes sin alterar (0 a 9)** | **0 alertas de severidad media o mayor**; 4 avisos informativos (PSI de `monto_medio_previo` de 0,109 a 0,132) | `docs/simulacion/resultados.md` |
| Alertas totales (pasos 0 a 25) | 68 (47 de severidad media o mayor); `MOD-DES-2` (crítica) en los pasos 17, 21 y 25 | `docs/alertas.csv` |
| AUC-PR | lotes 0 a 13: de 0,927 a 0,991 (v1); lotes 14 a 17: de 0,537 a 0,717 (v1); 18 a 21: de 0,536 a 0,682 (v4); 22 y 23: 0,785 y 0,749 (v5) | `docs/simulacion/negocio_por_lote.csv` |
| Duración | 49 s por paso (lote + monitoreo); `entrenar` de 28 a 29 s en Kestra | `docs/simulacion/resultados.md`, Kestra |

## Fase 5 · Reentrenamiento, promoción y rollback

| Paso | Disparo | Champion → challenger | Pérdida/1.000 (champion / challenger) | Mejora (umbral 4,51) | Regla | Decisión |
|---|---|---|---|---|---|---|
| 12 | calendario | v1 → v3 | 16,20 / 18,30 | −2,10 | rechazar | rechazada |
| 17 | desempeño | v1 → v4 | 446,08 / 368,45 | +77,63 | promover | aprobada |
| 21 | desempeño | v4 → v5 | 241,63 / 124,72 | +116,91 | promover | aprobada |
| 25 | desempeño | v5 → v6 | 96,74 / 101,21 | −4,48 | rechazar | rechazada |

- Umbral de promoción 4,51 = desviación (ddof = 1) de la pérdida por 1.000 entre los pliegues de la CV (39,30; 33,84; 30,35).
- **Rollback:** v5 → v4 y v4 → v5, cada uno visible en `GET /modelo` a los 30,1 s, sin reconstruir la imagen (mismo digest) — `docs/demos/rollback.csv`.
- **Demostraciones:** deriva 1 min 6 s; reentrenamiento ~35 s hasta la pausa (en el lote 21 la regla recomienda promover: +39,64); rollback ~30 s; respaldo < 1 s — `docs/demos/guion_video.md`.
- **Incidente:** pausa 1 (fallo de tipo en `REENTRENAMIENTOS`; decisión registrada fuera de Kestra con el mismo código; corrección en `49a5a12`) — `docs/simulacion/incidentes.md`.

## Fase 7 · Resultado de negocio y ética

| Cifra | Valor | Fuente |
|---|---|---|
| **Pérdida neta, lotes etiquetados 0 a 23 (308.056 transacciones)** | modelo **USD 33.340**; reglas fijas USD 473.566 (**−93,0 %**); sin modelo USD 870.612 (**−96,2 %**) | notebook 07, `docs/negocio/negocio_por_lote.csv` |
| Pérdida por 1.000, lotes sin alterar | modelo de 12,1 a 64,8; reglas de 1.469 a 1.510 | `negocio_por_lote.csv` |
| Errores (lotes 0 a 23) | 348 falsos negativos (USD 28.415); 871 falsas alarmas en verificar (USD 4.355); 114 legítimas retenidas (USD 570) | `docs/etica/costo_errores.csv` |
| Equidad por género (lotes sin alterar) | falsas alarmas: mujeres 0,315 % y hombres 0,243 % (1,30 veces; p = 0,003); fraudes detectados: 96,1 % y 98,9 % | `docs/etica/subgrupos.csv`, `etica.md` |
| Criterios de retirada | R1 negocio: no (máximo 0,309 de la pérdida de las reglas); **R2 equidad: sí** (8 de 21 ventanas por género); R3 montos fuera de soporte: no (máximo 0,159 % del lote; 252 transacciones, 0 fraudes, 245 aprobadas); R4 sistema: no (p95 de 17 ms, 0 respuestas 5xx) | `docs/etica/criterios_retirada.csv` |
| Predicciones exportadas | muestra trazable de 6.398 de 338.152 (1.956 fraudes, 1.146 alertas, 3.296 del 1 % restante) | `docs/predicciones.csv` |

## Gráficos (ruta → para qué)

| Gráfico | Uso sugerido |
|---|---|
| `docs/arquitectura.png` | arquitectura de punta a punta y patrón online |
| `docs/modelo_dimensional.png` | star schema y grano |
| `docs/eda/target_distribucion.png`, `heatmap_spearman.png`, `boxplots_por_clase.png`, `fraude_por_hora_y_categoria.png` | EDA (PSet 3) |
| `docs/features/evidencia_features_derivadas.png`, `ablacion_features.png` | features (PSet 3) |
| `docs/modelos/comparacion_baseline_candidatos.png` | líneas base y candidatos |
| `docs/tuning/tuning_mejora.png`, `tuning_configuraciones.png`, `tuning_tasa_aprendizaje.png` | tuning |
| `docs/seleccion/prueba_pr_y_perdida.png`, `perdida_vs_umbral_cv.png`, `importancia_permutacion.png` | selección y explicabilidad |
| `docs/api/umbral_retener.png` | segundo umbral (retener) |
| `docs/hallazgos/monto_vs_p95.png` | hallazgo B1 (montos fuera de soporte) |
| `docs/monitoreo/umbral_desempeno.png` | umbral de desempeño: CV semanal frente a la CV por pliegue |
| `docs/simulacion/lotes_prevalencia.png` | construcción de los lotes y prevalencia (D1) |
| `docs/simulacion/deriva_d2_montos_horas.png` | qué alteró D2 |
| `docs/simulacion/trafico_api.png` | latencia y decisiones por lote |
| `docs/monitoreo/psi_por_lote.png` | diagnóstico de deriva de datos |
| `docs/monitoreo/auc_pr_por_lote.png` | deriva conceptual y reentrenamientos |
| `docs/monitoreo/alertas_por_paso.png` | alertas por severidad |
| `docs/negocio/negocio_por_lote.png`, `negocio_acumulado.png` | resultado de negocio frente a las reglas y a no hacer nada |
| `docs/etica/subgrupos.png` | equidad por género y edad |

Capturas que tomaste o que faltan: Kestra (ejecución de la ingesta y pausa de aprobación), Swagger de la API, GitHub
Actions en verde con la imagen en GHCR, comparación de corridas en MLflow, tablero en `:8501`.
