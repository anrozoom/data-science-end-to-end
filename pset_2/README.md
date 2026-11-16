# PSet 2 · Centinela: pipeline de datos end-to-end

Pipeline ELT reproducible para el proyecto **Centinela** (detección de fraude con tarjeta de crédito):

**Kaggle (Sparkov) → Kestra → RAW → dbt → BRONZE → dbt → SILVER → dbt → GOLD → Spark → OBT**, con Snowflake como destino.

> Estado: **etapa 2** (infraestructura local y Snowflake). Las secciones de ingesta, dbt y Spark se completan en las etapas siguientes.

## Estructura

```
pset_2/
├── docker-compose.yml   Kestra + Postgres, clúster Spark y dbt
├── .env.example         Nombres de las variables (copiar a .env, que no se sube)
├── scripts/             generar_secretos_kestra.sh (crea .env.kestra para Kestra)
├── kestra/              Flows de Kestra
├── dbt/                 Proyecto de dbt y Dockerfile de su imagen
├── spark/               Job de Spark que construye la OBT
├── secrets/             Llave privada de Snowflake (no se sube; solo .gitkeep)
└── docs/                Evidencia para el documento técnico
```

## Requisitos

- Un Codespace de este repositorio con **4 núcleos y 16 GB** ("Change machine type"). Con 2 núcleos no caben Kestra y Spark a la vez.
- Docker y Docker Compose (ya vienen en el Codespace).

## 1. Variables de entorno

Desde `pset_2/`:

```bash
cp .env.example .env
```

Abre `.env` y reemplaza los valores ficticios. Para levantar la infraestructura basta con las tres variables de Kestra; las de Snowflake y Kaggle se llenan en las etapas 2 y 3. Escribe los valores sin comillas y sin el carácter `$`.

Cuando estén las credenciales de Snowflake y Kaggle (y la llave en `secrets/snowflake_key.p8`), genera los secretos que leen los flows de Kestra:

```bash
bash scripts/generar_secretos_kestra.sh
```

## 2. Levantar la infraestructura

```bash
cd pset_2
docker compose up -d
docker compose ps
```

| Servicio | Dónde se ve | Notas |
|---|---|---|
| Kestra | Puerto **8080** (pestaña Ports → globo) | Usuario y contraseña: los de `KESTRA_ADMIN_*` en `.env` |
| Spark master (UI) | Puerto **8081** | Si no aparece en Ports, agrégalo a mano con "Forward a Port" |
| Spark job (UI) | Puerto **4040** | Solo mientras corre un job |
| Postgres de Kestra | Sin puerto expuesto | Solo lo usa Kestra |

dbt no arranca con `up`: se ejecuta cuando se necesita.

```bash
docker compose run --rm dbt --version
```

## 3. Snowflake (una sola vez)

1. Genera el par de llaves en `secrets/` (la privada, cifrada; queda fuera de git):

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
3. Completa la sección Snowflake de `.env` (`SNOWFLAKE_ACCOUNT` = resultado de la consulta `snowflake_account` del script; `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`).
4. Verifica la conexión y los permisos:

   ```bash
   docker compose run --rm -v ./scripts:/scripts:ro --entrypoint python dbt /scripts/verificar_snowflake.py
   ```

5. Genera los secretos de Kestra y reinícialo:

   ```bash
   bash scripts/generar_secretos_kestra.sh
   docker compose up -d kestra
   ```

## 4. Apagar

```bash
docker compose down
```

Sin `-v`, los volúmenes se conservan: los flows y el historial de Kestra (`centinela_datos_postgres`, `centinela_datos_kestra`) y el CSV descargado de Kaggle (`centinela_datos_fuente`). **`docker compose down -v` los borra.**

## Memoria

Límites definidos en el compose (máquina de 16 GB):

| Componente | Límite |
|---|---|
| Kestra | 2,5 GB |
| Postgres de Kestra | 512 MB |
| Spark master (daemon + driver) | 1,5 GB |
| Spark worker (2 núcleos, 2 GB para ejecutores) | 3 GB |
| dbt (solo mientras corre) | 1 GB |
| Contenedor de cada tarea Python de Kestra | 1 GB, fijado en el flow; el backfill corre de a una ejecución |
| **Pico total** | **≈ 9,5 GB** |
