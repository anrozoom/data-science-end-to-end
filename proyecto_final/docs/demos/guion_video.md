# Guion de demostraciones para el video (máximo 7 minutos)

Todo desde `proyecto_final/` con la infraestructura levantada (`docker compose up -d`). Tiempos medidos el 2026-11-27.
Las demostraciones usan pasos y lotes >= 100 y quedan fuera de los resúmenes de la simulación.

| # | Parte del video | Comando | Duración medida | Qué se ve |
|---|---|---|---|---|
| 1 | Levantar la infraestructura | `docker compose up -d` y `docker compose ps` | ~1 min si las imágenes ya están | Kestra (8080), Spark (8081), MLflow (5055), API (8000), tablero (8501) |
| 2 | Ingesta hasta la OBT | `bash scripts/demo_ingesta.sh` | 3 min 45 s | Kestra: `cargar_raw` → `dbt_build` → `spark_obt` → `validar_obt` en una ejecución |
| 3 | Predicción válida y entrada inválida | `curl` de la sección «Fase 2» del README (o Swagger en `:8000/docs`) | segundos | 200 con decisión, versión, run_id e id; 422 que nombra el campo |
| 4 | Lote con deriva que dispara alertas | `bash scripts/demo_deriva.sh` | 1 min 6 s | Log de `monitoreo` (WARN): `DAT-PSI` de `categoria`, `SIS-VOL`, `MOD-TASA` |
| 5 | Reentrenamiento con aprobación | `bash scripts/demo_reentrenamiento.sh` | ~35 s hasta la pausa (`entrenar` tarda de 28 a 29 s en Kestra) | Log de `aviso`: v5 230,99 frente a challenger 191,35 por 1.000 → la regla recomienda promover. Resume → `aprobar = true` → `GET /modelo` muestra la versión nueva |
| 6 | Rollback | `bash scripts/demo_rollback.sh 5 restaurar` | ~30 s | Alias `champion` → v5; `GET /modelo` cambia solo (recarga cada 30 s) y el digest de la imagen no cambia |
| 7 | Interruptor de respaldo | `bash scripts/demo_respaldo.sh` | < 1 s | Misma transacción: `retener` con el modelo; `verificar` con las reglas fijas en respaldo; 401 sin token |

Notas:
- La demostración 5 crea una versión nueva de `centinela-modelo` (tag `motivo = demostración`, paso 101) y la deja con
  el alias `challenger`. Con el lote 21 se comparan dos modelos que no lo vieron: la v5 (entrenada hasta el lote 18) y
  el challenger (hasta el lote 20). Los ensayos en los lotes 20, 22 y 23 recomendaban rechazar (−1,15, −10,86 y −4,48).
- El rollback ya se demostró fuera del video (v5 → v4 → v5): `docs/demos/rollback.csv`.
