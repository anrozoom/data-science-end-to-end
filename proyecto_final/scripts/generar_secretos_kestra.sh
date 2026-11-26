#!/usr/bin/env bash
# Genera pset_2/.env.kestra a partir de pset_2/.env y de la llave privada.
#
# Kestra open source lee los secretos de variables de entorno con prefijo SECRET_
# y valor en base64; en un flow se usan como {{ secret('NOMBRE') }}.
# Tú solo escribes valores normales en .env; este script los codifica.
#
# Uso, desde pset_2/:
#     bash scripts/generar_secretos_kestra.sh
#     docker compose up -d kestra     # para que Kestra lea los secretos nuevos
#
# .env.kestra queda con permisos 600 y está en .gitignore: nunca se sube.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTRADA="$RAIZ/.env"
SALIDA="$RAIZ/.env.kestra"
LLAVE="$RAIZ/secrets/snowflake_key.p8"

# Variables de .env que necesitan los flows de Kestra.
NOMBRES=(
  SNOWFLAKE_ACCOUNT
  SNOWFLAKE_USER
  SNOWFLAKE_ROLE
  SNOWFLAKE_WAREHOUSE
  SNOWFLAKE_DATABASE
  SNOWFLAKE_PRIVATE_KEY_PASSPHRASE
  KAGGLE_API_TOKEN
)

if [[ ! -f "$ENTRADA" ]]; then
  echo "No existe $ENTRADA. Créalo con: cp .env.example .env" >&2
  exit 1
fi

# Lee el valor de una variable de .env sin ejecutar el archivo (no usa "source").
leer() {
  local nombre=$1
  sed -n "s/^${nombre}=//p" "$ENTRADA" | tail -n 1 | sed 's/\r$//'
}

umask 077
: > "$SALIDA"
# chmod explícito: en /workspaces las ACL por defecto ignoran el umask.
chmod 600 "$SALIDA"
for nombre in "${NOMBRES[@]}"; do
  valor="$(leer "$nombre")"
  if [[ -z "$valor" ]]; then
    echo "  (omitido) $nombre: vacío o ausente en .env"
    continue
  fi
  # Si sigue con el valor ficticio de .env.example, todavía no está configurada.
  if [[ -f "$RAIZ/.env.example" ]] && [[ "$valor" == "$(sed -n "s/^${nombre}=//p" "$RAIZ/.env.example" | tail -n 1)" ]] \
     && [[ "$nombre" != SNOWFLAKE_USER && "$nombre" != SNOWFLAKE_ROLE && "$nombre" != SNOWFLAKE_WAREHOUSE && "$nombre" != SNOWFLAKE_DATABASE ]]; then
    echo "  (omitido) $nombre: todavía tiene el valor ficticio de .env.example"
    continue
  fi
  printf 'SECRET_%s=%s\n' "$nombre" "$(printf '%s' "$valor" | base64 -w0)" >> "$SALIDA"
  echo "  SECRET_$nombre"
done

if [[ -f "$LLAVE" ]]; then
  printf 'SECRET_SNOWFLAKE_PRIVATE_KEY=%s\n' "$(base64 -w0 < "$LLAVE")" >> "$SALIDA"
  echo "  SECRET_SNOWFLAKE_PRIVATE_KEY (desde secrets/snowflake_key.p8)"
else
  echo "  (omitido) SECRET_SNOWFLAKE_PRIVATE_KEY: todavía no existe secrets/snowflake_key.p8"
fi

echo "Listo: $SALIDA (permisos 600). Reinicia Kestra para que lo lea: docker compose up -d kestra"
