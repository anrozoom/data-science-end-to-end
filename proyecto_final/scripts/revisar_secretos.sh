#!/usr/bin/env bash
# Revisa lo que está en staging (git diff --staged) antes de un commit del proyecto final:
#   1. ningún valor real de proyecto_final/.env (ni de pset_2/.env / pset_3/.env) aparece en el diff;
#   2. no hay llaves privadas, la llave pública, tokens de Kaggle (KGAT_) ni claves de Gemini (AIza);
#   3. no se agrega .env, .env.kestra, llaves ni datos (.parquet);
#   4. todo lo agregado está dentro de los prefijos permitidos (por defecto, proyecto_final/).
# No imprime ningún valor. Termina con código 1 si encuentra algo.
# Uso, desde la raíz del repo:  bash proyecto_final/scripts/revisar_secretos.sh [prefijos permitidos...]
set -uo pipefail
RAIZ="$(git rev-parse --show-toplevel)"; cd "$RAIZ"
DIFF="$(git diff --staged)"; fallas=0
PERMITIDOS="${*:-proyecto_final/}"
NO_SECRETOS='^(SNOWFLAKE_USER|SNOWFLAKE_ROLE|SNOWFLAKE_WAREHOUSE|SNOWFLAKE_DATABASE|SNOWFLAKE_PRIVATE_KEY_PATH|MLFLOW_TRACKING_URI|SNOWFLAKE_ENV_FILE|GEMINI_MODEL)$'

for env in proyecto_final/.env pset_2/.env pset_3/.env; do
  [[ -f "$env" ]] || continue
  ejemplo="${env}.example"
  while IFS='=' read -r k v; do
    [[ -z "$k" || "$k" =~ ^# || -z "$v" ]] && continue
    [[ "$k" =~ $NO_SECRETOS ]] && continue
    [[ -f "$ejemplo" && "$v" == "$(sed -n "s/^${k}=//p" "$ejemplo" | tail -n 1)" ]] && continue
    if grep -qF -- "$v" <<<"$DIFF"; then echo "ALERTA: el valor real de $k ($env) aparece en el diff"; fallas=1; fi
  done < "$env"
done

for pub in proyecto_final/secrets/snowflake_key.pub pset_2/secrets/snowflake_key.pub; do
  [[ -f "$pub" ]] || continue
  cuerpo="$(grep -v -- '-----' "$pub" | tr -d '\n')"
  if [[ -n "$cuerpo" ]] && grep -qF -- "${cuerpo:20:40}" <<<"$DIFF"; then echo "ALERTA: la llave pública ($pub) aparece en el diff"; fallas=1; fi
done

if grep -nE -- '-----BEGIN [A-Z ]*PRIVATE KEY-----|KGAT_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{30,}' <<<"$DIFF"; then
  echo "ALERTA: posible llave privada o token en el diff"; fallas=1
fi
if git diff --staged --name-only | grep -E '(^|/)\.env($|\.kestra$)|\.p8$|\.pub$|\.pem$|\.parquet$'; then
  echo "ALERTA: archivo de credenciales o de datos en staging"; fallas=1
fi
fuera=$(git diff --staged --name-only | while read -r a; do ok=0; for p in $PERMITIDOS; do [[ "$a" == $p* ]] && ok=1; done; [[ $ok == 0 ]] && echo "$a"; done)
if [[ -n "$fuera" ]]; then echo "ALERTA: archivos fuera de: $PERMITIDOS"; echo "$fuera"; fallas=1; fi

[[ $fallas -eq 0 ]] && echo "Revisión de secretos: LIMPIA ($(git diff --staged --name-only | wc -l) archivos, en: $PERMITIDOS)"
exit $fallas
