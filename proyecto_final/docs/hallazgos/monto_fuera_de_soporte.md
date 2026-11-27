# Hallazgo: el modelo es más permisivo con montos muy por encima de lo normal para su categoría

**Prueba:** `tests/test_comportamiento.py::test_b1_monto_muy_por_encima_del_p95_no_baja_la_probabilidad`, marcada como `xfail(strict=True)`. Es el "1 xfailed" de CI.

## Qué se esperaba

Si una compra igual a otra, del mismo cliente y en la misma categoría, tiene un monto mucho mayor (más de 5 veces el p95 de su categoría), su riesgo **no** debería bajar.

## Qué hace el modelo (muestra fija de prueba: 2.012 fraudes)

Se lleva el monto de cada fraude a `max(monto, k × p95 de su categoría)` y se recalcula `monto_relativo` con el mismo historial (`docs/hallazgos/monto_alto_decisiones_fraudes.csv`):

| Monto llevado a | La probabilidad baja | Δ prob. (mediana / media) | La decisión empeora | En retener (antes → después) | Quedarían aprobados |
|---|---|---|---|---|---|
| 2× p95 | 43,2 % | 0,000 / −0,093 | 14,3 % | 91,6 % → 79,9 % | 11,0 % |
| **5× p95** | **90,8 %** | **−0,021 / −0,125** | **22,6 %** | 91,6 % → **73,0 %** | **9,3 %** |
| 10× p95 | 92,6 % | −0,025 / −0,126 | 23,3 % | 91,6 % → 72,2 % | 8,7 % |

La curva completa está en `docs/hallazgos/monto_vs_p95.png` y `monto_vs_p95.csv`: la probabilidad media de los fraudes sube con el monto hasta ~2× p95 (0,85) y después baja un poco (0,82 en 5×). En las legítimas pasa lo mismo.

**Lectura:** el riesgo casi nunca cae a cero (la mediana del cambio es −0,02), pero en **uno de cada cinco fraudes la decisión se vuelve más permisiva**, por ejemplo de retener a verificar.

## Por qué: falta de soporte en los datos simulados

En el entrenamiento (`docs/hallazgos/soporte_entrenamiento.csv`):
- el fraude más caro vale **USD 1.376**;
- hay 2.674 transacciones con monto > 3× p95 de su categoría y solo 125 son fraude;
- hay **780 transacciones con monto > 5× p95 y ninguna es fraude** (0 de 780).

El modelo aprendió fielmente lo que muestran los datos de Sparkov: "monto altísimo = legítima". En un banco real, un fraude de varios miles de dólares es plausible y el modelo nunca vio uno.

## Qué se hace

1. **No se maquilla:** la prueba queda como `xfail(strict=True)`. Si un modelo futuro corrigiera el comportamiento, la prueba fallaría como `XPASS` y obligaría a revisar este hallazgo.
2. **Criterio de retirada y salvaguarda** (fase 7): las transacciones con monto fuera del soporte de entrenamiento (> 3× p95 de su categoría) se vigilan aparte en el monitoreo. Si el monitoreo muestra fraudes no detectados en esa franja, se pasa a revisión humana obligatoria.
3. **Limitación** del documento técnico: el modelo solo es confiable dentro del rango de montos que vio. Para producción hacen falta datos reales con fraudes de monto alto, o una regla de negocio complementaria.
