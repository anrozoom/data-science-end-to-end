#!/usr/bin/env bash
# curl autenticado contra la API de Kestra (usuario y contraseña de proyecto_final/.env; no los imprime).
# Uso:  bash scripts/kestra_api.sh [opciones de curl] /ruta        p. ej.  bash scripts/kestra_api.sh /executions/search
# Las rutas relativas se resuelven contra http://localhost:8080/api/v1/main (KESTRA_API para cambiarlo).
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API=${KESTRA_API:-http://localhost:8080/api/v1/main}
U=$(sed -n 's/^KESTRA_ADMIN_USER=//p' "$RAIZ/.env" | tail -n 1)
P=$(sed -n 's/^KESTRA_ADMIN_PASSWORD=//p' "$RAIZ/.env" | tail -n 1)
args=()
for a in "$@"; do
  if [[ "$a" == /* && "$a" != /workspaces* && "$a" != /tmp* ]]; then args+=("$API$a"); else args+=("$a"); fi
done
curl -s -u "$U:$P" "${args[@]}"
