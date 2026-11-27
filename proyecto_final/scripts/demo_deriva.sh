#!/usr/bin/env bash
# Demo de deriva para el video (~1,5 min): un lote con deriva (lote 100 = lote 15 con D1 y D2) pasa por la API
# y por el monitoreo en Kestra; el log del monitoreo muestra las alertas (WARN). Es una demostración: queda fuera
# de los resúmenes de la simulación (pasos y lotes >= 100).
# Uso, desde proyecto_final/:  bash scripts/demo_deriva.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 simulacion/lote_demo.py 2>&1 | grep -v -i warn
COMMIT=$(git rev-parse --short HEAD)
ID=$(bash scripts/kestra_api.sh -X POST -F paso_inicio=100 -F paso_fin=100 -F "git_commit=$COMMIT" \
     "/executions/centinela.produccion/produccion_lotes?labels=tipo:demo" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
echo "Kestra: http://localhost:8080/ui/main/executions/centinela.produccion/produccion_lotes/$ID"
bash scripts/esperar_ejecucion.sh "$ID" 600
python3 - <<'PY' 2>&1 | grep -v -i warn
import sys; sys.path.insert(0, "src")
from produccion import Snowflake, INICIO_SIM_SQL
a = Snowflake().sql(f"SELECT SEVERIDAD, MENSAJE FROM PRODUCCION.ALERTAS WHERE INICIO_SIMULACION = {INICIO_SIM_SQL} AND PASO = 100 ORDER BY SEVERIDAD")
print(f"Alertas del lote de demostración ({len(a)}):")
for _, r in a.iterrows():
    print("  " + r["mensaje"])
PY
