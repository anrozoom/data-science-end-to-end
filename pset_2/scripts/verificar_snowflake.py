"""Verifica la conexión del usuario de servicio con Snowflake y sus permisos.

Corre dentro del contenedor de dbt (trae snowflake-connector-python), desde pset_2/:

    docker compose run --rm -v ./scripts:/scripts:ro --entrypoint python dbt /scripts/verificar_snowflake.py

Lee la configuración de las variables SNOWFLAKE_* (pset_2/.env) y se autentica con
la llave privada cifrada de /secrets. No imprime credenciales ni el identificador
de la cuenta. Solo crea objetos TEMPORARY, que Snowflake borra al cerrar la sesión.
"""
import os
import sys

import snowflake.connector

ESQUEMAS = ["RAW", "BRONZE", "SILVER", "GOLD", "OBT"]


def main() -> int:
    cfg = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "role": os.environ["SNOWFLAKE_ROLE"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database": os.environ["SNOWFLAKE_DATABASE"],
        "private_key_file": os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        "private_key_file_pwd": os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
        "authenticator": "SNOWFLAKE_JWT",
    }
    fallos = 0

    def prueba(nombre, sql, mostrar=False):
        nonlocal fallos
        try:
            fila = cur.execute(sql).fetchone()
            print(f"  OK    {nombre}" + (f": {fila}" if mostrar else ""))
            return fila
        except Exception as e:  # noqa: BLE001 - se reporta cualquier fallo
            fallos += 1
            print(f"  FALLA {nombre}: {type(e).__name__}: {str(e).splitlines()[0]}")
            return None

    print("1) Autenticación con par de llaves")
    con = snowflake.connector.connect(**cfg)
    cur = con.cursor()
    prueba("sesión", "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), "
                     "CURRENT_DATABASE(), CURRENT_VERSION()", mostrar=True)

    print("2) Huella de la llave registrada en Snowflake")
    try:
        cur.execute(f"DESC USER {cfg['user']}")
        huella = [r[1] for r in cur.fetchall() if r[0] == "RSA_PUBLIC_KEY_FP"]
        print(f"  OK    RSA_PUBLIC_KEY_FP: {huella[0] if huella else '(no visible)'}")
    except Exception as e:  # noqa: BLE001
        print(f"  (info) DESC USER no permitido para el rol: {str(e).splitlines()[0]}")

    print("3) Warehouse")
    prueba("enciende y ejecuta una consulta (USAGE/OPERATE)", "SELECT 1")
    # Mismo valor que ya tiene: comprueba MODIFY sin cambiar nada.
    prueba("MODIFY (AUTO_SUSPEND = 60, sin cambio)",
           f"ALTER WAREHOUSE {cfg['warehouse']} SET AUTO_SUSPEND = 60")
    cur.execute(f"SHOW WAREHOUSES LIKE '{cfg['warehouse']}'")
    cols = [c[0] for c in cur.description]
    w = dict(zip(cols, cur.fetchone()))
    print(f"  info  size={w['size']} auto_suspend={w['auto_suspend']} "
          f"auto_resume={w['auto_resume']} resource_monitor={w['resource_monitor']}")
    print("  info  (resource_monitor puede verse null para un rol que no es ACCOUNTADMIN;"
          " confírmalo en Snowsight con SHOW WAREHOUSES como ACCOUNTADMIN)")

    print("4) Permisos por esquema (objetos TEMPORARY, se borran solos)")
    for esq in ESQUEMAS:
        prueba(f"{esq}: USAGE + CREATE TABLE",
               f"CREATE TEMPORARY TABLE {cfg['database']}.{esq}._verificacion (x INT)")
        prueba(f"{esq}: CREATE STAGE",
               f"CREATE TEMPORARY STAGE {cfg['database']}.{esq}._verificacion_stage")

    print("5) Lectura de consumo (SNOWFLAKE.USAGE_VIEWER)")
    prueba("WAREHOUSE_METERING_HISTORY",
           "SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY", mostrar=True)

    con.close()
    print(f"\nResultado: {'TODO OK' if fallos == 0 else f'{fallos} prueba(s) fallaron'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
