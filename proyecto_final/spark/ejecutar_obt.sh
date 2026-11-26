#!/usr/bin/env bash
# Ejecuta el job de la OBT en el clúster Spark del compose.
#
# spark-submit corre dentro de spark-master (driver en modo cliente) y envía los
# ejecutores al worker. Corre como root solo para poder leer la llave privada
# montada en /secrets (permisos 600). Las variables SNOWFLAKE_* llegan al contenedor
# desde pset_2/.env (env_file de spark-master en docker-compose.yml).
#
# Versiones fijas: Spark 3.5.3 (imagen) + spark-snowflake_2.12:3.1.1 (compilado para
# Spark 3.5) + snowflake-jdbc 3.19.0 (la versión que declara ese conector).
#
# Uso, desde pset_2/:  bash spark/ejecutar_obt.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PAQUETES="net.snowflake:spark-snowflake_2.12:3.1.1,net.snowflake:snowflake-jdbc:3.19.0"

docker compose exec -T -u root spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages "$PAQUETES" \
  --conf spark.jars.ivy=/tmp/.ivy2 \
  --conf spark.driver.memory=1g \
  --conf spark.executor.memory=1800m \
  --conf spark.executor.cores=2 \
  /opt/spark-jobs/construir_obt.py
