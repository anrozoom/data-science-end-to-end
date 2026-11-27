# Verificación desde un clon limpio (fase 8)

Fecha: 2026-11-27. Clon nuevo de `anrozoom/data-science-end-to-end` (rama `master`, commit `a6dcce7`) en una carpeta
temporal, sin `.env`, sin llaves y sin datos locales.

| # | Verificación | Resultado |
|---|---|---|
| 1 | Estructura obligatoria del PDF (`docker-compose.yml`, `.env.example`, `requirements.txt`, `README.md`, `.github/workflows/ci.yml` y `cd.yml`, los 4 flujos de `kestra/`, `dbt/`, `spark/`, `src/datos.py`, `pipeline.py` y `reentrenar.py`, notebooks 01 a 07, `api/`, `monitoreo/deriva.py` y `alertas.py`, `tests/` con sus fixtures, y en `docs/`: diagramas, `cambios.md`, los 5 CSV e `historial/`) | **Completa**: no falta ningún archivo |
| 2 | Llaves privadas, tokens de Kaggle (`KGAT_`) o claves de Gemini (`AIza`) en **todo el historial** de git (`git log -p --all`) | **0** coincidencias |
| 3 | Cada valor real de `proyecto_final/.env`, `pset_2/.env` y `pset_3/.env` buscado en todo el historial (`git log --all -S`) | **Ninguno** aparece |
| 4 | Archivos sensibles alguna vez versionados (`.env`, `.env.kestra`, `.p8`, `.pem`, `CLAUDE*.md`) | **Ninguno** |
| 5 | `Co-Authored-By` en los commits de `proyecto_final/` | **0** |
| 6 | `ci.yml` y `cd.yml`: copia en la raíz = copia en `proyecto_final/.github/workflows/`; `pruebas.yml` del profesor intacto | **Idénticas**; los tres workflows en verde en GitHub Actions |
| 7 | `python -m pytest -q tests` en el clon (sin servidor de MLflow ni Snowflake) | **26 pasan, 1 `xfail`** (hallazgo B1, esperado) |
| 8 | `docker compose config` con `.env.example` copiado como `.env` | **Válido**: servicios kestra-postgres, kestra, spark-master, spark-worker, mlflow, api y tablero, y con el perfil `tools` también dbt y ml |
| 9 | Notebooks 01 a 07 con su salida guardada | Todos ejecutados en orden desde 1 y **sin errores**. En el 06, la única celda sin salida es `sf.cerrar()`, que no imprime nada |
| 10 | Enlaces y rutas citadas en `README.md` y `docs/**/*.md` | Se encontraron 23 rotos: los de los docs del PSet 2 copiados en `docs/datos/` (quedaron un nivel más abajo), 4 que apuntaban a archivos reemplazados en la fase 1 y 1 del README. **Corregidos**: quedan 0 |

**Lo que no se ejecutó desde el clon, y por qué:**
- **La cadena con Snowflake** (ingesta completa, simulación, reentrenamientos): reescribiría `RAW…OBT` y la simulación
  vigente. Ya está verificada en el Codespace: la OBT reconstruida tiene la misma huella que el snapshot del PSet 3
  (`docs/obt_huella_referencia.json`) y la simulación completa está en `docs/simulacion/resultados.md`.
- **La construcción de las imágenes:** la de la API se construye y se publica en cada push (`ci.yml` y `cd.yml`), y las de
  `ml` y `tablero` se construyeron en el Codespace desde estos mismos archivos. Con 3,4 GB libres en disco no se repitieron.
- **El registro de modelos** vive en los volúmenes de MLflow (`centinela_mlflow_backend` y `centinela_mlflow_artefactos`),
  no en git. Para otra máquina, el README explica cómo recrear el snapshot y el registro (pasos 3 a 5).
