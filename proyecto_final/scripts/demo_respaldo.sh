#!/usr/bin/env bash
# Demo del interruptor de respaldo para el video (< 30 s): enciende el respaldo (reglas fijas del PSet 1),
# predice la misma transacción, lo apaga y vuelve a predecir. Token de proyecto_final/.env (no se imprime).
# Evidencia: docs/demos/respaldo.json.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
API=${API_URL:-http://localhost:8000}
TOKEN=$(sed -n 's/^ADMIN_TOKEN=//p' .env | tail -n 1)
SOL=docs/api/ejemplo_solicitud.json
resumen() { python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps({k: d.get(k) for k in ('decision','probabilidad','modelo','version_modelo','respaldo','motivo_respaldo')}, ensure_ascii=False))"; }
echo "1) Modelo en uso:";               curl -s "$API/modelo" | python3 -c "import json,sys; d=json.load(sys.stdin); print('  v'+str(d['version']), 'respaldo =', d['respaldo'])"
echo "2) Predicción normal:";           A=$(curl -s -X POST "$API/predecir" -H 'Content-Type: application/json' --data @$SOL); echo "  $(echo "$A" | resumen)"
echo "3) Interruptor ENCENDIDO:";       curl -s -X POST "$API/respaldo" -H "X-Token: $TOKEN" -H 'Content-Type: application/json' -d '{"activo": true}'; echo
echo "4) Misma transacción en respaldo:"; B=$(curl -s -X POST "$API/predecir" -H 'Content-Type: application/json' --data @$SOL); echo "  $(echo "$B" | resumen)"
echo "5) Sin token se rechaza:";        curl -s -o /dev/null -w "  HTTP %{http_code}\n" -X POST "$API/respaldo" -H 'Content-Type: application/json' -d '{"activo": false}'
echo "6) Interruptor APAGADO:";         curl -s -X POST "$API/respaldo" -H "X-Token: $TOKEN" -H 'Content-Type: application/json' -d '{"activo": false}'; echo
echo "7) De nuevo con el modelo:";      C=$(curl -s -X POST "$API/predecir" -H 'Content-Type: application/json' --data @$SOL); echo "  $(echo "$C" | resumen)"
python3 - "$A" "$B" "$C" <<'PY'
import json, sys
from datetime import datetime, timezone
d = {"ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
     "normal": json.loads(sys.argv[1]), "respaldo": json.loads(sys.argv[2]), "restaurado": json.loads(sys.argv[3])}
open("docs/demos/respaldo.json", "w", encoding="utf-8").write(json.dumps(d, indent=2, ensure_ascii=False))
PY
