# PSet 3 · Centinela: experimentación y selección del modelo

Modelo de detección de fraude para el proyecto **Centinela**: puntuar cada transacción con tarjeta en el momento de la autorización. Parte de la OBT construida en el PSet 2 (`CENTINELA.OBT.TRANSACCIONES_OBT` en Snowflake) y termina con un modelo registrado en MLflow como `centinela-modelo@champion`.

📄 **Documento técnico:** [PSet3_memo_Zuniga_Salvador.pdf](docs/PSet3_memo_Zuniga_Salvador.pdf)

**OBT → EDA → Features → Pipeline → Línea base → Candidatos → Tuning → Selección → Model Registry**

## Estructura

```
pset_3/
├── docker-compose.yml          MLflow 2.17.2: backend store SQLite + artifact store (volúmenes), puerto 5055
├── .env.example                Variables (MLflow, ruta de credenciales de Snowflake, clave de Gemini)
├── requirements.txt            Versiones fijas
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_features.ipynb
│   ├── 03_baseline_candidatos.ipynb
│   ├── 04_tuning.ipynb
│   ├── 05_seleccion.ipynb
│   └── 06_reproduccion.ipynb   Reproducción del champion desde el Model Registry
├── src/
│   ├── datos.py                Snapshot de la OBT (Snowflake → Parquet) con fecha de corte y SHA-256
│   ├── pipeline.py             Features, Pipeline + ColumnTransformer, CV temporal, reglas fijas y métricas
│   └── experimento.py          Registro de corridas en MLflow (datos, tags, métricas, modelo con firma)
└── docs/                       Evidencia: tablas (CSV) y gráficos (PNG) de cada notebook, y corridas.csv
    └── PSet3_memo_Zuniga_Salvador.pdf   Documento técnico del PSet 3
```

`data/` (el snapshot en Parquet) y `.env` no se suben a git.

## 1. Requisitos

- El Codespace del curso, con 4 núcleos y 16 GB. Python 3.11 y Docker vienen incluidos.
- Las librerías del curso más dos nuevas:

  ```bash
  pip install -r pset_3/requirements.txt
  ```

- Acceso a la OBT en Snowflake: el par de llaves del usuario de servicio del PSet 2 (`pset_2/.env` y `pset_2/secrets/`). Solo hace falta para crear el snapshot.
- Una clave gratuita de Google AI Studio, solo para la prueba del LLM del notebook 03.

## 2. Configuración

Desde `pset_3/`:

```bash
cp .env.example .env
chmod 600 .env
```

| Variable | Valor |
|---|---|
| `MLFLOW_TRACKING_URI` | `http://127.0.0.1:5055`, el servidor de este PSet. Los notebooks lo fijan explícitamente, así que no usan el MLflow del devcontainer (5050) |
| `SNOWFLAKE_ENV_FILE` | Archivo con las variables `SNOWFLAKE_*`. Por defecto, `../pset_2/.env` |
| `GEMINI_API_KEY` | Clave de <https://aistudio.google.com/apikey> |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite`. `gemini-2.5-flash` ya no está disponible para cuentas nuevas, y `gemini-3.8-flash` devolvía 503 por alta demanda |

## 3. Levantar MLflow

```bash
cd pset_3
docker compose up -d
curl -s http://127.0.0.1:5055/health     # OK
```

La interfaz está en el **puerto 5055**: pestaña Ports → globo. Experimento: **`centinela`**. Los datos persisten en los volúmenes `centinela_mlflow_backend` y `centinela_mlflow_artefactos`. `docker compose down` los conserva y **`docker compose down -v` los borra**.

## 4. Conexión a Snowflake y snapshot de la OBT

```bash
cd pset_3
python src/datos.py
```

Descarga `CENTINELA.OBT.TRANSACCIONES_OBT` completa (1.852.394 filas y 40 columnas, ~20 s) y deja:
- `data/obt_snapshot.parquet`, fuera de git;
- `data/obt_snapshot.json`, con la tabla de origen, la **fecha de corte**, las filas y el **SHA-256**.

Los notebooks solo leen el Parquet, y `cargar_obt()` verifica el hash antes de devolver los datos. Cada corrida de MLflow registra la tabla, la fecha de corte y el hash.

**Con otra cuenta de Snowflake:** recrea la OBT con el PSet 2 (`pset_2/README.md`), pon las variables `SNOWFLAKE_*` en un `.env` y apunta a él con `SNOWFLAKE_ENV_FILE`. La autenticación es por par de llaves (`SNOWFLAKE_PRIVATE_KEY_PATH` y `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`). Si la ruta de la llave es la de los contenedores (`/secrets/...`), `datos.py` la busca en la carpeta `secrets/` junto al `.env`. Un snapshot nuevo tendrá otra fecha de corte y quizá otro hash, y las corridas lo registran.

## 5. Orden de ejecución de los notebooks

Ejecuta cada uno con **Restart + Run All**, en orden, con MLflow levantado. Cada notebook **borra sus propias corridas anteriores** (por la etiqueta `fase`) antes de registrar las nuevas, así que repetirlo no duplica corridas.

| # | Notebook | Qué hace | Tiempo aprox. (4 núcleos) |
|---|---|---|---|
| 1 | `01_eda.ipynb` | Tamaño, tipos, nulos, descriptivos, target, atípicos IQR/Z, Spearman, desbalance y hallazgos | 1 min |
| 2 | `02_features.ipynb` | Features derivadas, ablación pareada y prueba de no fuga | 3 min |
| 3 | `03_baseline_candidatos.ipynb` | 2 líneas base, 4 familias tabulares y Gemini por prompting | 4 min |
| 4 | `04_tuning.ipynb` | Búsqueda aleatoria con 30 configuraciones de los 3 mejores (corridas hijas) | ~1–1,5 h |
| 5 | `05_seleccion.ipynb` | Ganador frente al segundo en CV, umbral por costo en CV, **corridas finales** (`fase=final`): reentrenamiento, una sola evaluación en prueba y registro `@champion`/`@challenger`; exporta `docs/corridas.csv` | ~5 min |
| 6 | `06_reproduccion.ipynb` | **Notebook limpio**: no importa nada de `src/` ni del 05. Verifica el hash del snapshot, carga `models:/centinela-modelo@champion` y reproduce con `==` la AUC-PR y la pérdida neta registradas (imprime `REPRODUCIDO: True`) | <1 min |

Para ejecutarlos desde la terminal, igual que Restart + Run All:

```bash
cd pset_3/notebooks
jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=10800 01_eda.ipynb
```

## 6. Decisiones de diseño (resumen)

- **División única:** el hold-out es la partición de prueba del PSet 1 (jul–dic 2020, 525.661 filas, 0,383 % de fraude). Solo se usa en el notebook 05, una vez, con el ganador y el segundo.
- **CV:** `TimeSeriesSplit(3)` sobre entrenamiento (ene-2019 a jun-2020, 1.326.733 filas), ordenado por tiempo. No se usa `GroupKFold` por cliente porque el banco puntúa a sus propios clientes, que ya tienen historial.
- **Cómputo:** cada pliegue se **ajusta** con todos los fraudes y el **5 % de las legítimas**, y se **valida con todas las filas**, a la prevalencia real. El modelo final se ajusta igual sobre todo el entrenamiento y se evalúa sobre toda la prueba.
- **Métricas:**
  - Técnica: **AUC-PR**. En entrenamiento se pondera a la prevalencia real para que la brecha mida sobreajuste.
  - De negocio: **pérdida neta** = fraude no detectado + USD 5 por falsa alarma, con el umbral elegido en la CV.
- **Sin fuga:** la preparación (imputación, one-hot, escalado y el p95 por categoría) vive en `src/pipeline.py` dentro de un `Pipeline` ajustado solo con el bloque de entrenamiento. Las columnas excluidas y sus motivos están en `pipeline.EXCLUIDAS`.

## 7. Resultados

| | Valor |
|---|---|
| Corridas en el experimento `centinela` | 102 activas: 2 líneas base, 5 candidatos, 93 de tuning (3 padre + 90 hijas) y 2 finales ([`docs/corridas.csv`](docs/corridas.csv)) |
| Champion | `centinela-modelo` **versión 1** (`@champion`): HistGradientBoosting con hiperparámetros por defecto, `run_id 70bfd857902b4cc188d52a94d934c442` |
| Challenger | `centinela-modelo` **versión 2** (`@challenger`): RandomForest tuneado, `run_id 24f82ec738f8412c9de7599f4e0051a2` |
| AUC-PR | CV 0,9612 ± 0,0163 · **prueba 0,9655** |
| Umbral (elegido en la CV) | 0,2400 |
| Pérdida neta en prueba | **USD 14.649**, frente a USD 779.426 de las reglas fijas (**−98,1 %**), con 0,29 % de legítimas alertadas |
| Reproducción | `06_reproduccion.ipynb`: `REPRODUCIDO: True` |

Las decisiones, los resultados del tuning y las limitaciones están en [`docs/decisiones_y_limitaciones.md`](docs/decisiones_y_limitaciones.md). La evidencia de cada notebook está en `docs/eda/`, `docs/features/`, `docs/modelos/`, `docs/tuning/` y `docs/seleccion/`.
