#!/usr/bin/env bash
# Espera a que una ejecución de Kestra (y sus subflujos) termine o quede en PAUSA; imprime su estado.
# Uso: bash scripts/esperar_ejecucion.sh <id_ejecucion> [segundos_max=3600]
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ID=$1; MAX=${2:-3600}; t0=$(date +%s)
while true; do
  estado=$(bash "$RAIZ/scripts/kestra_api.sh" "/executions/$ID" | python3 -c "import json,sys; print(json.load(sys.stdin)['state']['current'])")
  # (la API de búsqueda de Kestra 2.0 ignora el filtro state=; se filtra aquí)
  pausadas=$(bash "$RAIZ/scripts/kestra_api.sh" "/executions/search?namespace=centinela.produccion&size=50" \
             | python3 -c "import json,sys; print(' '.join(e['flowId']+':'+e['id'] for e in json.load(sys.stdin).get('results',[]) if e['state']['current']=='PAUSED'))")
  if [[ -n "$pausadas" ]]; then echo "PAUSA $pausadas (principal: $estado, $(( $(date +%s) - t0 )) s)"; exit 0; fi
  case "$estado" in SUCCESS|FAILED|KILLED|WARNING|CANCELLED) echo "FIN $estado ($(( $(date +%s) - t0 )) s)"; exit 0;; esac
  (( $(date +%s) - t0 > MAX )) && { echo "TIEMPO AGOTADO ($estado)"; exit 1; }
  sleep 15
done
