#!/usr/bin/env bash
# Demo de reentrenamiento para el video (~1 min hasta la pausa): lanza reentrenamiento.yml (paso de demostración
# 101, evaluación en el lote 21) y se detiene cuando llega a la PAUSA de aprobación. Medido en ensayo: champion
# v5 230,99 frente a challenger 191,35 por 1.000 -> la regla recomienda promover.
# Después, en Kestra: Executions -> la ejecución PAUSED -> Resume -> aprobar = true -> la API cambia de versión.
# Para volver a la v5:  bash scripts/demo_rollback.sh 5 restaurar
# Uso, desde proyecto_final/:  bash scripts/demo_reentrenamiento.sh [lote_evaluacion=21]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
COMMIT=$(git rev-parse --short HEAD)
ID=$(bash scripts/kestra_api.sh -X POST -F paso=101 -F motivo=demostración -F "lote_evaluacion=${1:-21}" -F "git_commit=$COMMIT" \
     "/executions/centinela.produccion/reentrenamiento?labels=tipo:demo" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
echo "Kestra: http://localhost:8080/ui/main/executions/centinela.produccion/reentrenamiento/$ID"
bash scripts/esperar_ejecucion.sh "$ID" 600
bash scripts/kestra_api.sh "/logs/$ID" | python3 -c "
import json,sys
for l in json.load(sys.stdin):
    if l.get('taskId') == 'aviso': print(l['message'])"
