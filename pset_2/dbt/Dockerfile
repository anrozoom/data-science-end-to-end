# Imagen de dbt Core con el adaptador de Snowflake para el PSet 2.
# Se construye sola con: docker compose run --rm dbt --version
# Versiones fijas: dbt-core y dbt-snowflake de la misma versión menor (1.11).
FROM python:3.11-slim

RUN pip install --no-cache-dir \
        dbt-core==1.11.16 \
        dbt-snowflake==1.11.6

# Carpeta donde se monta el proyecto de dbt (pset_2/dbt/).
WORKDIR /usr/app/dbt

# HOME escribible para cualquier usuario: dbt guarda ahí archivos temporales.
ENV HOME=/tmp

ENTRYPOINT ["dbt"]
CMD ["--version"]
