# PSet 2 · Centinela: pipeline de datos end-to-end

Pipeline ELT reproducible del proyecto **Centinela** (detección de fraude con tarjeta de crédito en el momento de la autorización):

**Kaggle (Sparkov) → Kestra → RAW → dbt → BRONZE → dbt → SILVER → dbt → GOLD (star schema) → Spark → OBT**, con **Snowflake** como destino.

| Capa | Tabla en Snowflake (`CENTINELA`) | Filas |
|---|---|---|
| RAW | `RAW.TRANSACCIONES` | 1.852.394 |
| BRONZE | `BRONZE.BRZ_TRANSACCIONES` | 1.852.394 |
| SILVER | `SILVER.SLV_TRANSACCIONES` | 1.852.394 |
| GOLD | `GOLD.FCT_TRANSACCIONES` + `DIM_CLIENTE` (999), `DIM_COMERCIO` (693), `DIM_CATEGORIA` (14), `DIM_FECHA` (731), `DIM_HORA` (24) | 1.852.394 en el hecho |
| OBT | `OBT.TRANSACCIONES_OBT` | 1.852.394 |

Documentación y evidencia en [`docs/`](docs/):
- [arquitectura y batch frente a streaming](docs/arquitectura.md)
- [ingesta](docs/ingesta.md)
- [calidad de datos](docs/calidad_datos.md)
- [modelo dimensional y tests](docs/modelo_dimensional.md)
- [OBT](docs/obt.md)
- [limitaciones](docs/limitaciones.md)

## Estructura

```
pset_2/
├── docker-compose.yml        Kestra + Postgres, clúster Spark (master + worker) y dbt
├── .env.example              Nombres de las variables (copiar a .env, que no se sube)
├── README.md
├── kestra/
│   ├── flows/ingesta_diaria.yml   Flow: trigger diario, retry, errors, concurrencia
│   ├── ingesta/                   Imagen centinela-ingesta (Dockerfile + cargar_dia.py)
│   ├── desplegar_flows.sh         Crea o actualiza los flows en Kestra por la API
│   └── backfill_paralelo.sh       Backfill del histórico, una ejecución por fecha
├── dbt/                      Proyecto dbt (bronze/silver/gold, tests) y Dockerfile de su imagen
├── spark/                    construir_obt.py + ejecutar_obt.sh
├── snowflake/01_setup.sql    Base, esquemas, warehouse, rol, usuario de servicio y resource monitor
├── scripts/                  Secretos de Kestra, verificación de Snowflake, diagnóstico de calidad,
│                             validación SQL de la OBT y revisión de secretos antes de cada commit
├── secrets/                  Llave privada de Snowflake (no se sube; solo .gitkeep)
└── docs/                     Evidencia para el documento técnico
```

## Requisitos

- Un Codespace de este repositorio con **4 núcleos y 16 GB** ("Change machine type").
- Una cuenta de Snowflake con el rol `ACCOUNTADMIN` (solo para el paso 3) y un token de la API de Kaggle (formato `KGAT_…`, en kaggle.com → Settings → API).

Todos los comandos se corren **desde `pset_2/`**.

## 1. Variables de entorno

```bash
cd pset_2
cp .env.example .env
chmod 600 .env
```

Abre `.env` y reemplaza los valores ficticios: Kestra (usuario y contraseña de la UI), Snowflake (paso 3) y `KAGGLE_API_TOKEN`. Escribe los valores sin comillas y sin el carácter `$`.

> **Si cambias `.env` después de levantar los servicios,** los contenedores que ya existen siguen con los valores viejos: Docker Compose lee `.env` (y `.env.kestra`) solo al **crear** cada contenedor. Regenera los secretos y recrea los servicios con el comando del paso 3.5. dbt no lo necesita, porque `docker compose run` crea un contenedor nuevo en cada ejecución.

## 2. Infraestructura local

```bash
docker compose up -d
docker compose ps
```

| Servicio | Dónde se ve | Notas |
|---|---|---|
| Kestra | Puerto **8080** (pestaña Ports → globo) | Usuario y contraseña: `KESTRA_ADMIN_*` de `.env` |
| Spark master (UI) | Puerto **8081** | Si no aparece en Ports, agrégalo con "Forward a Port" |
| Spark job (UI) | Puerto **4040** | Solo mientras corre un job |
| Postgres de Kestra | Sin puerto expuesto | Solo lo usa Kestra |

dbt no arranca con `up`: se ejecuta con `docker compose run --rm dbt ...`. Construye su imagen una vez (si se omite, el primer `run` la construye igual, pero antes muestra un aviso `pull access denied` al intentar bajarla de Docker Hub):

```bash
docker compose build dbt
```

## 3. Snowflake (una sola vez)

1. Par de llaves en `secrets/`. La privada queda cifrada; elige una passphrase y guárdala en `.env` como `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`:

   ```bash
   openssl genrsa 2048 | openssl pkcs8 -topk8 -v2 aes-256-cbc -inform PEM -out secrets/snowflake_key.p8
   chmod 600 secrets/snowflake_key.p8
   openssl rsa -in secrets/snowflake_key.p8 -pubout -out secrets/snowflake_key.pub
   grep -v -- '-----' secrets/snowflake_key.pub | tr -d '\n'; echo   # cuerpo de la llave pública
   ```

2. En Snowsight, con el rol `ACCOUNTADMIN`, ejecuta [`snowflake/01_setup.sql`](snowflake/01_setup.sql) reemplazando `<PEGA_AQUI_LA_LLAVE_PUBLICA>`. Crea:
   - el warehouse XS `CENTINELA_WH` y el resource monitor `CENTINELA_RM` (15 créditos al mes);
   - la base `CENTINELA` con los esquemas `RAW`, `BRONZE`, `SILVER`, `GOLD` y `OBT`;
   - el rol `CENTINELA_ROLE` y el usuario de servicio `CENTINELA_SVC`, que solo entra con la llave.
3. En `.env`, pon `SNOWFLAKE_ACCOUNT` = resultado de la consulta `snowflake_account` del script.
4. Verifica la conexión y los permisos (debe terminar en `Resultado: TODO OK`):

   ```bash
   docker compose run --rm -v ./scripts:/scripts:ro --entrypoint python dbt /scripts/verificar_snowflake.py
   ```

5. Genera los secretos de Kestra y **recrea** Kestra y Spark para que lean los valores nuevos (Kestra los secretos de `.env.kestra`; `spark-master` las variables `SNOWFLAKE_*` de `.env`, que usa el job de la OBT):

   ```bash
   bash scripts/generar_secretos_kestra.sh
   docker compose up -d --force-recreate kestra spark-master spark-worker
   ```

   Comprobación: `docker compose exec -T spark-master sh -c 'env | grep -c ^SNOWFLAKE_'` debe mostrar `7`.

## 4. Ingesta con Kestra → RAW

Requiere que `KAGGLE_API_TOKEN` estuviera en `.env` al correr el paso 3.5 (si no, el flow falla al buscar el secreto: complétalo y repite el paso 3.5).

```bash
docker build -t centinela-ingesta:1.0 kestra/ingesta   # imagen que corren las tareas (pullPolicy NEVER)
bash kestra/desplegar_flows.sh                          # sube centinela.ingesta.ingesta_diaria
```

- **Probar un día:** en Kestra → Flows → `ingesta_diaria` → **Execute**, con `fecha = 2019-01-01`. La primera ejecución descarga la fuente de Kaggle (~20 s) y la divide por día.
- **Probar el retry:** lo mismo con `simular_falla = true`. El intento 0 falla a propósito y el intento 1 recarga el día (idempotente).
- **Trigger:** `Schedule` diario a las 02:00 UTC (queda activo al desplegar el flow).
- **Backfill del histórico:**
  - Nativo, desde la UI: pestaña **Triggers** → `diario` → **Backfill executions**, de 2019-01-01 a 2021-01-01. En Kestra 2.0.7 emite las ejecuciones de a una (~67 min para 731 días).
  - En paralelo, el mismo flow con concurrencia 16 (~8 min):

    ```bash
    bash kestra/backfill_paralelo.sh 2019-01-01 2020-12-31
    ```

Resultado esperado: 1.852.394 filas en `RAW.TRANSACCIONES`. Detalle en [`docs/ingesta.md`](docs/ingesta.md).

## 5. Diagnóstico de calidad (sobre RAW)

```bash
docker compose run --rm -v ./scripts:/scripts:ro -v ./docs:/docs --entrypoint python dbt /scripts/diagnostico_calidad.py
```

Escribe `docs/calidad_resultados.md` con las 19 consultas y sus resultados reales. Las decisiones de limpieza están en [`docs/calidad_datos.md`](docs/calidad_datos.md).

## 6. dbt: BRONZE → SILVER → GOLD

```bash
docker compose run --rm dbt debug   # conexión (el "git ERROR" es esperado: la imagen no trae git y no se usan paquetes)
docker compose run --rm dbt build   # modelos + 67 tests
```

Resultado esperado: `PASS=75 WARN=0 ERROR=0`. Ver [`docs/modelo_dimensional.md`](docs/modelo_dimensional.md).

## 7. Spark: OBT

```bash
bash spark/ejecutar_obt.sh
docker compose run --rm -v ./scripts:/scripts:ro --entrypoint python dbt /scripts/validar_obt_sql.py   # validación SQL independiente
```

El job imprime el JSON de validaciones y escribe `OBT.TRANSACCIONES_OBT` (~2 min). Si un chequeo falla, no escribe. Ver [`docs/obt.md`](docs/obt.md).

## 8. Apagar

```bash
docker compose down
```

Sin `-v` se conservan los volúmenes: los flows y el historial de Kestra (`centinela_datos_postgres`, `centinela_datos_kestra`) y el CSV de Kaggle (`centinela_datos_fuente`). **`docker compose down -v` los borra.**

## Memoria

Límites definidos en el compose (máquina de 16 GB):

| Componente | Límite |
|---|---|
| Kestra | 2,5 GB |
| Postgres de Kestra | 512 MB |
| Spark master (daemon + driver) | 1,5 GB |
| Spark worker (2 núcleos, 2 GB para ejecutores) | 3 GB |
| dbt (solo mientras corre) | 1 GB |
| Contenedor de cada tarea de ingesta | 1 GB de límite |

Con la concurrencia de 16 del backfill, la suma **teórica** de los límites de los contenedores de tarea es de 16 GB, más que la máquina. En la práctica, cada tarea solo sube un CSV de ~2.500 filas: el backfill completo terminó sin errores de memoria. Su consumo real no se midió. Para el backfill conviene no correr Spark al mismo tiempo. Si la máquina se queda corta, baja `concurrency.limit` en el flow.

## Seguridad

- Credenciales solo en `.env`, `.env.kestra` y `secrets/`, todos ignorados por git.
- Antes de cada commit: `bash scripts/revisar_secretos.sh`, desde la raíz del repo, con los archivos ya agregados.
