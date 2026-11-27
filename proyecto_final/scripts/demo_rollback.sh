#!/usr/bin/env bash
# Demo de rollback para el video (< 1 min): mueve el alias champion a otra versión y muestra que GET /modelo
# cambia SOLO (recarga periódica de la API), sin reconstruir la imagen. Evidencia: docs/demos/rollback.csv.
# Uso, desde proyecto_final/:
#   bash scripts/demo_rollback.sh 4             # rollback a la v4
#   bash scripts/demo_rollback.sh 5 restaurar   # vuelve a la v5
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
echo "Imagen del contenedor de la API (no cambia): $(docker inspect -f '{{.Config.Image}} {{.Image}}' centinela-final-api-1 | cut -c1-90)"
python3 scripts/mover_alias.py "${1:?versión destino}" --motivo "${2:-rollback}" 2>&1 | grep -v -i warn
echo "Imagen del contenedor de la API (después):   $(docker inspect -f '{{.Config.Image}} {{.Image}}' centinela-final-api-1 | cut -c1-90)"
