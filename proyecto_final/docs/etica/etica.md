# Ética operativa: subgrupos, costo de los errores y criterios de retirada

Cifras de `monitoreo/etica.py` (salidas en `docs/etica/`) sobre las predicciones de la simulación con target llegado
(lotes 0 a 23, `data/predicciones_completas.parquet`), unidas al snapshot de la OBT para el género. **El género no es una
entrada del modelo** (se excluyó por equidad en el PSet 3): se usa solo para auditar. La edad sí es una entrada.

## 1. Desempeño y tasa de cada decisión por subgrupo

**Lotes sin alterar (0 a 9), champion v1**, que es la lectura limpia:

| Dimensión | Grupo | Transacciones | Fraudes | AUC-PR | Fraudes detectados | Falsas alarmas (% legítimas) | Legítimas retenidas | Aprobar | Verificar | Retener |
|---|---|---|---|---|---|---|---|---|---|---|
| total | total | 194.522 | 850 | 0,964 | 97,3 % | 0,282 % | 0,035 % | 99,29 % | 0,28 % | 0,43 % |
| genero | hombre | 88.129 | 358 | 0,982 | 98,9 % | 0,243 % | 0,034 % | 99,36 % | 0,22 % | 0,42 % |
| genero | mujer | 106.393 | 492 | 0,950 | 96,1 % | 0,315 % | 0,036 % | 99,24 % | 0,32 % | 0,44 % |
| grupo_edad | 25 a 39 | 61.312 | 282 | 0,965 | 97,9 % | 0,305 % | 0,038 % | 99,25 % | 0,30 % | 0,45 % |
| grupo_edad | 40 a 59 | 73.015 | 300 | 0,943 | 95,3 % | 0,296 % | 0,038 % | 99,31 % | 0,29 % | 0,39 % |
| grupo_edad | 60 o más | 43.289 | 222 | 0,983 | 98,6 % | 0,269 % | 0,023 % | 99,23 % | 0,26 % | 0,51 % |
| grupo_edad | menos de 25 | 16.906 | 46 | 0,990 | 100,0 % | 0,178 % | 0,042 % | 99,55 % | 0,14 % | 0,31 % |

**Todos los lotes etiquetados (0 a 23)**, que incluyen la deriva inducida y las versiones v1, v4 y v5:

| Dimensión | Grupo | Transacciones | Fraudes | AUC-PR | Fraudes detectados | Falsas alarmas (% legítimas) | Legítimas retenidas | Aprobar | Verificar | Retener |
|---|---|---|---|---|---|---|---|---|---|---|
| total | total | 308.056 | 1956 | 0,846 | 82,2 % | 0,322 % | 0,037 % | 99,16 % | 0,33 % | 0,51 % |
| genero | hombre | 138.972 | 909 | 0,856 | 82,6 % | 0,270 % | 0,031 % | 99,19 % | 0,27 % | 0,53 % |
| genero | mujer | 169.084 | 1047 | 0,836 | 81,9 % | 0,364 % | 0,042 % | 99,13 % | 0,37 % | 0,50 % |
| grupo_edad | 25 a 39 | 97.361 | 565 | 0,840 | 82,7 % | 0,371 % | 0,041 % | 99,15 % | 0,38 % | 0,47 % |
| grupo_edad | 40 a 59 | 116.325 | 727 | 0,849 | 82,7 % | 0,322 % | 0,045 % | 99,16 % | 0,32 % | 0,52 % |
| grupo_edad | 60 o más | 67.695 | 511 | 0,850 | 82,0 % | 0,289 % | 0,019 % | 99,09 % | 0,31 % | 0,59 % |
| grupo_edad | menos de 25 | 26.675 | 153 | 0,833 | 79,1 % | 0,226 % | 0,034 % | 99,32 % | 0,22 % | 0,46 % |

Gráfico: `docs/etica/subgrupos.png`.

## 2. Hallazgo de equidad: más falsas alarmas para las mujeres

- En los lotes sin alterar, **el 0,315 % de las compras legítimas de mujeres recibe una alerta, frente al 0,243 % de las
  de hombres: 1,30 veces** (334 de 105.901 frente a 213 de 87.771; prueba de dos proporciones, p = 0,003). Las mujeres
  también tienen menos fraudes detectados (96,1 % frente a 98,9 %).
- En ventanas móviles de 4 lotes (`equidad_por_ventana.csv`), la tasa de las mujeres es la más alta en 20 de 21
  ventanas, y en 8 la diferencia supera 1,25 y es significativa (p < 0,05). La primera son los
  lotes 2 a 5, sin deriva todavía (1,62 veces, p = 0,002).
- **No lo explica la mezcla de categorías:** si cada género tuviera la tasa de falsas alarmas de cada categoría del total,
  mujeres y hombres quedarían en 0,285 % y 0,279 %. La brecha está **dentro** de las categorías (por ejemplo,
  `food_dining` 0,42 % frente a 0,17 %; `misc_pos` 0,69 % frente a 0,38 %; `kids_pets` 0,31 % frente a 0,13 %).
- Causa probable: variables que actúan como sustituto del género (por ejemplo, el historial del cliente o la ocupación,
  que en Sparkov se asignan por perfil sintético). **No se verificó.** Queda como trabajo pendiente y como limitación.
- Por edad, el grupo más alto cambia de una ventana a otra (25 a 39, o 40 a 59); 6 de 21 ventanas superan el umbral.
  Sin una dirección estable, se vigila sin atribuirle una causa.
- Con 42 pruebas (21 ventanas × 2 dimensiones) al 5 %, se esperarían unos 2 falsos positivos. Las 8 ventanas por género,
  todas en la misma dirección, están muy por encima de eso.

## 3. Costo de cada tipo de error y quién lo asume (lotes 0 a 23)

| Error | Casos | Costo (supuesto del PSet 1) | Quién lo asume |
|---|---|---|---|
| falso negativo (fraude aprobado) | 348 | USD 28.415 | el banco (contracargo del monto) y el cliente (gestión de la disputa, tarjeta bloqueada y reemplazada) |
| falso positivo en verificar (legítima con OTP o llamada) | 871 | USD 4.355 | el banco (USD 5 por verificación, supuesto del PSet 1) y el cliente legítimo (fricción: un paso más para pagar) |
| falso positivo en retener (legítima retenida para el analista) | 114 | USD 570 | el cliente legítimo (compra detenida hasta la revisión; el costo real supera los USD 5 del supuesto) y el banco (tiempo del analista, riesgo de abandono) |

El supuesto de USD 5 por falsa alarma subestima el costo de **retener** a un cliente legítimo: su compra queda detenida
hasta que la revisa un analista. Por eso el segundo umbral se eligió con una precisión ≥ 90 % (fase 2), y solo el 0,037 % de
las legítimas termina retenida.

## 4. Criterios de retirada (evaluados en la simulación)

| Criterio | Métrica | Umbral | Respuesta | Observado en la simulación | ¿Se activó? |
|---|---|---|---|---|---|
| R1 negocio: el modelo pierde más que las reglas fijas | pérdida neta del modelo / pérdida de las reglas en el mismo lote etiquetado | > 1 en 2 lotes etiquetados seguidos | interruptor de respaldo (reglas fijas) y reentrenamiento urgente; comité de riesgo | máximo 0.309 (lote 20); lotes > 1: 0 | **no** |
| R2 equidad: falsas alarmas desiguales entre subgrupos | tasa de falsas alarmas (legítimas en verificar o retener) del grupo más alto / la del más bajo, por género y por grupo de edad, en ventanas móviles de 4 lotes (grupos con >= 30 falsas alarmas) | > 1.25 (regla de los 4/5) y diferencia significativa (dos proporciones, p < 0.05) | revisión de equidad por el comité de riesgo: análisis de causa (variables que actúan como proxy), ajuste de umbral o reentrenamiento con restricción de equidad; si no se corrige en el siguiente ciclo, retirar el modelo (respaldo general, nunca un trato distinto por grupo) | genero: 8 de 21 ventanas sobre el umbral (cociente máximo 1.88, mujer frente a hombre, lotes 20-23); grupo_edad: 6 de 21 ventanas sobre el umbral (cociente máximo 1.65, 25 a 39 frente a 40 a 59, lotes 11-14) | **sí** |
| R3 montos fuera de soporte (hallazgo B1) | % de transacciones del lote con monto > 5 × p95 de su categoría (zona donde el modelo baja la probabilidad, prueba B1 en xfail) | > 1 % del lote; y cualquier transacción en esa zona | regla de protección: esas transacciones van como mínimo a verificar; si superan el 1 % del lote, retirar el modelo (respaldo) hasta reentrenar con datos de esos montos | máximo 0.159 % del lote (lote 12); 252 transacciones en la zona (0 fraudes), 245 aprobadas por el modelo | **no** |
| R4 sistema: el servicio no responde a tiempo | latencia p95 de POST /predecir y tasa de 5xx por lote | p95 > 200 ms o 5xx > 1 % en el lote | interruptor de respaldo automático (reglas fijas) hasta restablecer el servicio; aviso a plataforma | p95 máximo 17.0 ms; 5xx totales 0 | **no** |

- **R2 se activa:** según su respuesta, el modelo pasa a revisión de equidad. No se retira de inmediato, porque frente
  a las reglas fijas reduce la pérdida en más del 90 % (R1). Pero si la brecha no se corrige en el siguiente ciclo, se
  retira. La respuesta nunca es un trato distinto por grupo (por ejemplo, umbrales por género), que sería discriminación directa.
- **R3 (montos fuera de soporte, hallazgo B1)** no llegó al 1 % de ningún lote. La regla de protección («como mínimo,
  verificar») habría enviado a verificación 245 compras aprobadas por el modelo, ninguna de ellas fraude en estos
  datos: USD 1.225 de costo de verificación a cambio de cubrir una zona donde el modelo no es confiable.
- R2 se definió con ventanas de 4 lotes porque **por lote** el cociente es ruido: cada subgrupo tiene de 0 a ~35 falsas
  alarmas por lote, y con 0 el cociente se vuelve infinito.
