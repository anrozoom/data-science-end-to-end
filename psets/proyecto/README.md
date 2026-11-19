# [Nombre de tu proyecto]

> Este es el README de tu proyecto: reemplaza cada sección entre corchetes a medida que avanzas. Escríbelo para alguien que clona tu fork sin haber estado en clase y necesita entender qué hace el proyecto y correrlo, no como una nota para ti.

[Un párrafo: qué problema de negocio resuelve, para quién, y qué predice el modelo. Sale de tu propuesta del PSet 1, que está completa en `docs/`.]

**Métrica de éxito:** [la métrica de negocio y el umbral de decisión del PSet 1]

## Datos

| Fuente | Qué contiene | Cómo se obtiene | Dónde queda |
|---|---|---|---|
| [nombre de la fuente] | [qué filas y columnas trae, desde qué fecha] | [la URL, la API o el procedimiento exacto] | `data/raw/[archivo]` |

Los datos no están en el repositorio. Para regenerarlos desde cero: [los comandos, en orden]. Se completa con el PSet 1.

## Cómo correr el pipeline de datos

El pipeline de datos del PSet 2 está en [`pset_2/`](../../pset_2/), en la raíz del repositorio, siguiendo el enunciado en PDF que entregó el profesor: **Kaggle → Kestra → Snowflake (RAW → BRONZE → SILVER → GOLD con dbt) → Spark (OBT)**. Los comandos en orden, desde qué carpeta se corren y el resultado esperado de cada etapa están en [`pset_2/README.md`](../../pset_2/README.md). La evidencia de cada etapa (ingesta, calidad de datos, modelo dimensional, OBT y limitaciones) está en [`pset_2/docs/`](../../pset_2/docs/).

**Batch o streaming:** al proyecto le alcanza con **batch diario**. En esta etapa, los datos alimentan el entrenamiento, la evaluación y el monitoreo del modelo: comparar contra las reglas fijas, ajustar umbrales y reentrenar cada mes. Esas decisiones **no pierden valor con datos de horas o días** de antigüedad, y la fuente se publica una vez al día (~2.500 transacciones). Streaming solo se justificaría cuando el modelo pase a decidir en línea, es decir, a aprobar, verificar o retener cada compra en el momento de la autorización. Ahí, un dato de hace horas sí pierde valor, porque la ventana de "transacciones en la última hora" tiene que incluir las de hace minutos. El detalle está en [`pset_2/docs/arquitectura.md`](../../pset_2/docs/arquitectura.md).

## Cómo entrenar y evaluar el modelo

La experimentación del PSet 3 está en [`pset_3/`](../../pset_3/), en la raíz del repositorio, siguiendo el enunciado en PDF que entregó el profesor: **OBT (Snowflake) → EDA → Features → Pipeline → Líneas base → Candidatos → Tuning → Selección → Model Registry**. Los pasos completos están en [`pset_3/README.md`](../../pset_3/README.md):
1. Levantar el MLflow del PSet 3: `cd pset_3 && docker compose up -d` (puerto **5055**).
2. Crear el snapshot de la OBT: `python src/datos.py`, con las credenciales del PSet 2.
3. Ejecutar con **Restart + Run All**, en este orden:
   - `01_eda`
   - `02_features`
   - `03_baseline_candidatos`
   - `04_tuning` (~1 h)
   - `05_seleccion`
   - `06_reproduccion`

La preparación sin fuga vive en `pset_3/src/pipeline.py` y los notebooks la importan. La evidencia de cada etapa está en [`pset_3/docs/`](../../pset_3/docs/), incluida `corridas.csv`.

## Modelo final

**`centinela-modelo` versión 1, alias `@champion`:** HistGradientBoosting con hiperparámetros por defecto, `run_id 70bfd857902b4cc188d52a94d934c442`, en el experimento `centinela` del MLflow del PSet 3.
- **CV:** AUC-PR 0,9612 ± 0,0163.
- **Prueba (jul-dic 2020):** AUC-PR 0,9655 y pérdida neta USD 14.649 con el umbral 0,2400, frente a USD 779.426 de las reglas fijas (−98,1 %).
- **Challenger (`@challenger`, versión 2):** RandomForest tuneado, `run_id 24f82ec738f8412c9de7599f4e0051a2`.

El razonamiento completo está en [`pset_3/docs/decisiones_y_limitaciones.md`](../../pset_3/docs/decisiones_y_limitaciones.md), y la reproducción exacta de la métrica, en `pset_3/notebooks/06_reproduccion.ipynb`.

## Cómo correr el servicio

[Cómo se construye y se levanta el contenedor de `servicio/`, qué versión del modelo carga desde el registro, y un ejemplo de petición con su respuesta. Se completa con el PSet 4.]
