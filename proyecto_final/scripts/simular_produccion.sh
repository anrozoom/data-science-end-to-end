#!/usr/bin/env bash
# Lanza la simulación de producción en Kestra (flujo centinela.produccion.produccion_lotes).
# Uso, desde proyecto_final/:  bash scripts/simular_produccion.sh [paso_inicio=0] [paso_fin=25]
# Requisitos: docker compose up -d (Kestra, MLflow, API); imagen centinela-ml:1.0 (docker compose build ml);
#             lotes construidos (python simulacion/construir_lotes.py); flujos desplegados (bash kestra/desplegar_flows.sh).
# La ejecución sigue en Kestra aunque se cierre la terminal. En cada reentrenamiento se detiene en la PAUSA
# de aprobación (Executions -> la ejecución de "reentrenamiento" -> Resume).
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INI=${1:-0}; FIN=${2:-25}
COMMIT=$(git -C "$RAIZ" rev-parse --short HEAD)$([[ -n "$(git -C "$RAIZ" status --porcelain -- .)" ]] && echo "-con-cambios" || true)
bash "$RAIZ/scripts/kestra_api.sh" -X POST \
  -F "paso_inicio=$INI" -F "paso_fin=$FIN" -F "git_commit=$COMMIT" \
  "/executions/centinela.produccion/produccion_lotes?labels=tipo:simulacion" \
  | python3 -c "import json,sys; e=json.load(sys.stdin); print('Ejecución', e['id'], e['state']['current'], '-> http://localhost:8080/ui/main/executions/centinela.produccion/produccion_lotes/' + e['id'])"
