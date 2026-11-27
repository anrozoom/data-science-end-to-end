#!/usr/bin/env bash
# Demo para el video: una ejecución corta de kestra/ingesta.yml (~3-4 min) en la que se ven las 4 tareas
# (cargar_raw, dbt_build, spark_obt y validar_obt) pasar a verde. Reescribe 2 días de RAW (forzar=true) y
# reconstruye GOLD y la OBT desde RAW completo, así que el resultado es el mismo de la reconstrucción total.
# Uso, desde proyecto_final/:  bash scripts/demo_ingesta.sh [fecha_inicio] [fecha_fin]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
INICIO=${1:-2020-12-30}; FIN=${2:-2020-12-31}
U=$(sed -n 's/^KESTRA_ADMIN_USER=//p' .env | tail -n 1); P=$(sed -n 's/^KESTRA_ADMIN_PASSWORD=//p' .env | tail -n 1)
API=${KESTRA_API:-http://localhost:8080/api/v1/main}
ID=$(curl -sf -u "$U:$P" -X POST "$API/executions/centinela.ingesta/ingesta?labels=tipo:demo" \
       -F fecha_inicio="$INICIO" -F fecha_fin="$FIN" -F forzar=true -F transformar=true \
     | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
echo "Ejecución de demo: $ID ($INICIO a $FIN). Ábrela en Kestra -> Executions -> $ID -> Gantt."
