#!/usr/bin/env bash
# Crea o actualiza en Kestra todos los flows de proyecto_final/kestra/ usando la API.
# Lee el usuario y la contraseña de la UI desde pset_2/.env (no los imprime).
# Uso, desde proyecto_final/:  bash kestra/desplegar_flows.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API=${KESTRA_API:-http://localhost:8080/api/v1/main}
U=$(sed -n 's/^KESTRA_ADMIN_USER=//p' "$RAIZ/.env" | tail -n 1)
P=$(sed -n 's/^KESTRA_ADMIN_PASSWORD=//p' "$RAIZ/.env" | tail -n 1)

for flow in "$RAIZ"/kestra/*.yml; do
  id=$(sed -n 's/^id: *//p' "$flow" | head -n 1)
  ns=$(sed -n 's/^namespace: *//p' "$flow" | head -n 1)
  if curl -sf -u "$U:$P" "$API/flows/$ns/$id" > /dev/null; then
    curl -sf -u "$U:$P" -X PUT -H "Content-Type: application/x-yaml" \
      --data-binary @"$flow" "$API/flows/$ns/$id" > /dev/null
    echo "Flow $ns.$id actualizado"
  else
    curl -sf -u "$U:$P" -X POST -H "Content-Type: application/x-yaml" \
      --data-binary @"$flow" "$API/flows" > /dev/null
    echo "Flow $ns.$id creado"
  fi
done
