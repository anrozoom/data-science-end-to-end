#!/usr/bin/env bash
# Revisa lo que está en staging (git diff --staged) antes de un commit:
#   1. que ningún valor real de pset_2/.env aparezca en el diff;
#   2. que no haya llaves privadas, tokens de Kaggle ni la llave pública;
#   3. que no se esté agregando .env, .env.kestra ni archivos de llaves;
#   4. que todo lo agregado esté dentro de pset_2/.
# No imprime ningún valor. Termina con código 1 si encuentra algo.
# Uso, desde la raíz del repo: bash pset_2/scripts/revisar_secretos.sh
set -uo pipefail

RAIZ="$(git rev-parse --show-toplevel)"
ENV="$RAIZ/pset_2/.env"
EJEMPLO="$RAIZ/pset_2/.env.example"
PUB="$RAIZ/pset_2/secrets/snowflake_key.pub"
DIFF="$(git -C "$RAIZ" diff --staged)"
fallas=0

if [[ -f "$ENV" ]]; then
  while IFS='=' read -r k v; do
    [[ -z "$k" || "$k" =~ ^# || -z "$v" ]] && continue
    [[ "$v" == "$(sed -n "s/^${k}=//p" "$EJEMPLO" | tail -n 1)" ]] && continue
    if grep -qF -- "$v" <<<"$DIFF"; then
      echo "ALERTA: el valor real de $k aparece en el diff"; fallas=1
    fi
  done < "$ENV"
fi

if [[ -f "$PUB" ]]; then
  cuerpo="$(grep -v -- '-----' "$PUB" | tr -d '\n')"
  if [[ -n "$cuerpo" ]] && grep -qF -- "${cuerpo:20:40}" <<<"$DIFF"; then
    echo "ALERTA: la llave pública aparece en el diff"; fallas=1
  fi
fi

if grep -nE -- '-----BEGIN [A-Z ]*PRIVATE KEY-----|KGAT_[A-Za-z0-9]{16,}' <<<"$DIFF"; then
  echo "ALERTA: posible llave privada o token en el diff"; fallas=1
fi

if git -C "$RAIZ" diff --staged --name-only | grep -E '(^|/)\.env($|\.kestra$)|\.p8$|\.pub$|\.pem$'; then
  echo "ALERTA: archivo de credenciales en staging"; fallas=1
fi

if git -C "$RAIZ" diff --staged --name-only | grep -v '^pset_2/'; then
  echo "ALERTA: hay archivos fuera de pset_2/ en staging"; fallas=1
fi

if [[ $fallas -eq 0 ]]; then
  echo "Revisión de secretos: LIMPIA ($(git -C "$RAIZ" diff --staged --name-only | wc -l) archivos en staging, todos en pset_2/)"
fi
exit $fallas
