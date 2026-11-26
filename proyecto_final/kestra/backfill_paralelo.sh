#!/usr/bin/env bash
# Backfill en paralelo del flow centinela.ingesta.ingesta_diaria.
#
# Por qué existe: el backfill nativo del trigger Schedule (pestaña Triggers > Backfill)
# funciona, pero en Kestra 2.0.7 emite las ejecuciones de a una (medido: ~1 cada 5,5 s,
# nunca más de una corriendo), así que 731 días tardan ~67 min aunque el flow permita
# 16 en paralelo. Este script crea una ejecución por fecha con el input "fecha"; el
# límite de concurrencia del flow (16, behavior QUEUE) las procesa en paralelo.
# La carga es idempotente, así que repetir una fecha no duplica filas.
#
# Uso, desde pset_2/:  bash kestra/backfill_paralelo.sh 2019-01-01 2020-12-31
set -euo pipefail

INICIO=${1:?fecha inicial AAAA-MM-DD}
FIN=${2:?fecha final AAAA-MM-DD}
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API=${KESTRA_API:-http://localhost:8080/api/v1/main}
U=$(sed -n 's/^KESTRA_ADMIN_USER=//p' "$RAIZ/.env" | tail -n 1)
P=$(sed -n 's/^KESTRA_ADMIN_PASSWORD=//p' "$RAIZ/.env" | tail -n 1)

fecha="$INICIO"
n=0
while [[ "$fecha" < "$FIN" || "$fecha" == "$FIN" ]]; do
  curl -sf -u "$U:$P" -X POST \
    "$API/executions/centinela.ingesta/ingesta_diaria?labels=tipo:backfill-paralelo" \
    -F "fecha=$fecha" > /dev/null
  n=$((n + 1))
  fecha=$(date -u -d "$fecha + 1 day" +%Y-%m-%d)
done
echo "Ejecuciones creadas: $n ($INICIO a $FIN). Kestra las procesa de a 16."
