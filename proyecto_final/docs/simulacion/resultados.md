# Resultados de la simulación de producción

Simulación vigente iniciada el 2026-11-27 a las 03:53:47 UTC. Ejecuciones de `produccion_lotes`: `7ST9UOarLtEZD4i1u2liB9`
(pasos 0 a 12) y `7RYaimmmy9MPEIKxM531D1` (pasos 13 a 25, tras el incidente de la pausa 1, ver `incidentes.md`).
Cifras: `alertas_por_paso.csv`, `reentrenamientos_simulacion.csv` y `negocio_por_lote.csv`, generados por
`simulacion/resumen_simulacion.py` desde `CENTINELA.PRODUCCION`.

## Reentrenamientos

| Paso | Disparo | Lote de evaluación | Champion | Challenger | Pérdida/1.000 champion | Pérdida/1.000 challenger | Mejora (umbral 4,51) | Regla | Decisión humana | Ejecución de Kestra |
|---|---|---|---|---|---|---|---|---|---|---|
| 12 | calendario | 10 | v1 | v3 | 16,20 | 18,30 | -2,10 | rechazar | **rechazada** | `6Flrm4ebd62EISjnBWTvad` (decisión registrada fuera de Kestra, ver incidentes) |
| 17 | desempeño | 15 | v1 | v4 | 446,08 | 368,45 | 77,63 | promover | **aprobada** | `31u65UU6JNDTgGNaTuSIkZ` |
| 21 | desempeño | 19 | v4 | v5 | 241,63 | 124,72 | 116,91 | promover | **aprobada** | `3wgThCLoWCtOUjqBB7ePbD` |
| 25 | desempeño | 23 | v5 | v6 | 96,74 | 101,21 | -4,48 | rechazar | **rechazada** | `25gX96ugw8BStmSTB3WNc2` |

La decisión humana coincidió con la regla en los 4 casos. El champion final es la **v5**; las v3 y v6 quedaron rechazadas.

## Alertas

**Lotes sin alterar (0 a 9): ninguna alerta de severidad media o mayor.** Hubo 4 avisos informativos (`DAT-PSI-AVISO`,
severidad baja, sin acción): paso 0: `monto_medio_previo` 0,132, paso 1: `monto_medio_previo` 0,128, paso 2: `monto_medio_previo` 0,127, paso 3: `monto_medio_previo` 0,109. Son el PSI natural de `monto_medio_previo` medido en la calibración (máximo 0,132),
así que no se ajustó ningún umbral. `MOD-DES-1` no saltó en ningún lote sin alterar.

Alertas de severidad media o mayor por paso (desde el paso 10, todas en lotes alterados):

| Paso | Lote | Alertas |
|---|---|---|
| 10 | 10 | DAT-PSI, SIS-VOL |
| 11 | 11 | DAT-PSI, SIS-VOL |
| 12 | 12 | DAT-PSI, MOD-TASA, SIS-VOL |
| 13 | 13 | DAT-PSI, MOD-TASA, SIS-VOL |
| 14 | 14 | DAT-PSI, SIS-VOL |
| 15 | 15 | DAT-PSI, SIS-VOL |
| 16 | 14 | MOD-DES-1 |
| 16 | 16 | DAT-PSI, SIS-VOL |
| 17 | 15 | MOD-DES-1, MOD-DES-2 |
| 17 | 17 | DAT-PSI, SIS-VOL |
| 18 | 16 | MOD-DES-1 |
| 18 | 18 | DAT-PSI, SIS-VOL |
| 19 | 17 | MOD-DES-1 |
| 19 | 19 | DAT-PSI, SIS-VOL |
| 20 | 18 | MOD-DES-1 |
| 20 | 20 | DAT-PSI, SIS-VOL |
| 21 | 19 | MOD-DES-1, MOD-DES-2 |
| 21 | 21 | DAT-PSI, SIS-VOL |
| 22 | 20 | MOD-DES-1 |
| 22 | 22 | DAT-PSI, SIS-VOL |
| 23 | 21 | MOD-DES-1 |
| 23 | 23 | DAT-PSI, SIS-VOL |
| 24 | 22 | MOD-DES-1 |
| 24 | 24 | DAT-PSI, SIS-VOL |
| 25 | 23 | MOD-DES-1, MOD-DES-2 |
| 25 | 25 | DAT-PSI, SIS-VOL |

- D1 (lotes 10 en adelante): `DAT-PSI` de `categoria` y `SIS-VOL` en todos los lotes, y `MOD-TASA` en los lotes 12 y
  13 (la tasa de alertas sube con la prevalencia). La deriva de datos sola **no** disparó reentrenamiento: la AUC-PR de
  los lotes 10 a 13 fue de 0,974 a 0,991, en parte por la prevalencia más alta.
- D2 (lotes 14 en adelante): `MOD-DES-1` en cada lote etiquetado y `MOD-DES-2` (crítica) en los pasos 17, 21 y 25, que
  dispararon los 3 reentrenamientos por desempeño. Los lotes 16 y 17 (servidos por la v1 después de que llegara la v4)
  dieron `MOD-DES-1`, pero no contaron para un disparo nuevo: la regla solo usa lotes del champion vigente.
- `MOD-PERD` (modelo peor que las reglas) no saltó en ningún lote.

## Resultado de negocio por lote etiquetado

Pérdida neta = fraude no detectado + USD 5 por falsa alarma, por 1.000 transacciones del lote. «Reglas» = las reglas
fijas del PSet 1 en el mismo lote; «sin modelo» = aprobar todo (todo el fraude se pierde). Los lotes 24 y 25 no
reciben target dentro de la simulación.

| Lote | Versión que lo sirvió | Deriva | Prevalencia | AUC-PR | Modelo | Reglas | Sin modelo |
|---|---|---|---|---|---|---|---|
| 0 | v1 | sin alterar | 0,330 % | 0,9271 | 24,03 | 1.475,00 | 1.302,65 |
| 1 | v1 | sin alterar | 0,400 % | 0,9354 | 25,25 | 1.469,32 | 2.139,01 |
| 2 | v1 | sin alterar | 0,450 % | 0,9823 | 12,11 | 1.505,12 | 2.339,83 |
| 3 | v1 | sin alterar | 0,310 % | 0,9565 | 18,06 | 1.488,01 | 1.513,08 |
| 4 | v1 | sin alterar | 0,470 % | 0,9713 | 15,29 | 1.479,07 | 2.393,91 |
| 5 | v1 | sin alterar | 0,660 % | 0,9688 | 17,18 | 1.510,12 | 3.040,72 |
| 6 | v1 | sin alterar | 0,320 % | 0,9535 | 30,52 | 1.478,06 | 1.590,06 |
| 7 | v1 | sin alterar | 0,490 % | 0,9782 | 64,85 | 1.477,90 | 2.612,14 |
| 8 | v1 | sin alterar | 0,340 % | 0,9784 | 19,55 | 1.500,43 | 2.106,02 |
| 9 | v1 | sin alterar | 0,630 % | 0,9741 | 50,46 | 1.499,42 | 3.528,55 |
| 10 | v1 | D1 | 0,790 % | 0,9739 | 16,20 | 1.423,77 | 5.403,76 |
| 11 | v1 | D1 | 0,760 % | 0,9816 | 207,77 | 1.450,40 | 4.854,46 |
| 12 | v1 | D1 | 1,570 % | 0,9811 | 191,99 | 1.515,81 | 8.391,72 |
| 13 | v1 | D1 | 1,730 % | 0,9911 | 39,30 | 1.501,45 | 9.231,16 |
| 14 | v1 | D1+D2 | 1,000 % | 0,5369 | 391,72 | 1.771,33 | 2.363,23 |
| 15 | v1 | D1+D2 | 1,480 % | 0,7174 | 446,08 | 1.784,29 | 5.234,69 |
| 16 | v1 | D1+D2 | 1,090 % | 0,6043 | 412,96 | 1.714,11 | 3.911,55 |
| 17 | v1 | D1+D2 | 0,730 % | 0,5857 | 264,20 | 1.588,04 | 1.862,23 |
| 18 | v4 | D1+D2 | 1,130 % | 0,6815 | 315,04 | 1.665,61 | 3.410,60 |
| 19 | v4 | D1+D2 | 0,610 % | 0,6021 | 241,63 | 1.673,04 | 1.780,07 |
| 20 | v4 | D1+D2 | 1,000 % | 0,5362 | 514,95 | 1.667,48 | 2.872,18 |
| 21 | v4 | D1+D2 | 0,910 % | 0,5901 | 379,60 | 1.695,82 | 2.995,16 |
| 22 | v5 | D1+D2 | 0,730 % | 0,7850 | 148,11 | 1.665,09 | 2.711,73 |
| 23 | v5 | D1+D2 | 0,660 % | 0,7487 | 96,74 | 1.572,36 | 1.958,39 |

**Total de los lotes 0 a 23** (308.056 transacciones): modelo **33.340 USD**, reglas fijas 473.566 USD,
sin modelo 870.612 USD.
