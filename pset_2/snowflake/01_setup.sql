-- =============================================================================
-- PSet 2 · Centinela · Configuración inicial de Snowflake
-- Ejecutar UNA vez en Snowsight (Projects > Worksheets) con el rol ACCOUNTADMIN.
-- Es idempotente: si se vuelve a correr, no duplica ni borra nada.
-- Antes de correrlo, reemplaza <PEGA_AQUI_LA_LLAVE_PUBLICA> en el bloque 6.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- -----------------------------------------------------------------------------
-- 1. Warehouse XS: cómputo mínimo, se apaga a los 60 s sin uso y se enciende
--    solo cuando llega una consulta. Nace apagado (no gasta hasta usarse).
-- -----------------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS CENTINELA_WH
  WAREHOUSE_SIZE      = 'XSMALL'
  AUTO_SUSPEND        = 60
  AUTO_RESUME         = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'PSet 2 Centinela: ingesta, dbt y Spark';

-- -----------------------------------------------------------------------------
-- 2. Resource monitor: tope de 15 créditos al mes sobre CENTINELA_WH.
--    50 % y 75 %: aviso por correo. 100 %: SUSPEND (termina lo que corre, no
--    acepta más). 110 %: SUSPEND_IMMEDIATE (cancela lo que esté corriendo).
-- -----------------------------------------------------------------------------
CREATE RESOURCE MONITOR IF NOT EXISTS CENTINELA_RM
  WITH CREDIT_QUOTA    = 15
       FREQUENCY       = MONTHLY
       START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 50  PERCENT DO NOTIFY
    ON 75  PERCENT DO NOTIFY
    ON 100 PERCENT DO SUSPEND
    ON 110 PERCENT DO SUSPEND_IMMEDIATE;

ALTER WAREHOUSE CENTINELA_WH SET RESOURCE_MONITOR = CENTINELA_RM;

-- -----------------------------------------------------------------------------
-- 3. Base de datos y un esquema por capa del pipeline.
-- -----------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS CENTINELA COMMENT = 'PSet 2 Centinela';
CREATE SCHEMA IF NOT EXISTS CENTINELA.RAW    COMMENT = 'Datos tal como llegan de Kaggle (Kestra)';
CREATE SCHEMA IF NOT EXISTS CENTINELA.BRONZE COMMENT = 'Copia 1:1 de RAW con tipos y nombres normalizados (dbt)';
CREATE SCHEMA IF NOT EXISTS CENTINELA.SILVER COMMENT = 'Datos limpios y deduplicados (dbt)';
CREATE SCHEMA IF NOT EXISTS CENTINELA.GOLD   COMMENT = 'Star schema (dbt)';
CREATE SCHEMA IF NOT EXISTS CENTINELA.OBT    COMMENT = 'One Big Table (Spark)';

-- -----------------------------------------------------------------------------
-- 4. Rol de servicio del pipeline. Se cuelga de SYSADMIN para que tú (como
--    SYSADMIN o ACCOUNTADMIN) veas en Snowsight todo lo que el pipeline crea.
-- -----------------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS CENTINELA_ROLE COMMENT = 'Rol de servicio del pipeline Centinela';
GRANT ROLE CENTINELA_ROLE TO ROLE SYSADMIN;

-- -----------------------------------------------------------------------------
-- 5. Permisos mínimos del rol.
--    Warehouse: USAGE (usarlo), OPERATE (encenderlo/apagarlo) y MODIFY (solo
--    para subir AUTO_SUSPEND durante el backfill y restaurarlo a 60).
--    Base y esquemas: usar y crear tablas, vistas, stages y formatos de archivo.
--    No puede borrar esquemas ni la base: no es su dueño.
-- -----------------------------------------------------------------------------
GRANT USAGE, OPERATE, MODIFY ON WAREHOUSE CENTINELA_WH TO ROLE CENTINELA_ROLE;

GRANT USAGE ON DATABASE CENTINELA TO ROLE CENTINELA_ROLE;

GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON SCHEMA CENTINELA.RAW    TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON SCHEMA CENTINELA.BRONZE TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON SCHEMA CENTINELA.SILVER TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON SCHEMA CENTINELA.GOLD   TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON SCHEMA CENTINELA.OBT    TO ROLE CENTINELA_ROLE;

-- Lectura del consumo de créditos (ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY),
-- para medir el costo real del piloto del backfill. Solo lectura.
GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE CENTINELA_ROLE;

-- -----------------------------------------------------------------------------
-- 6. Usuario de servicio. TYPE = SERVICE: no puede entrar con contraseña ni a
--    Snowsight; solo con el par de llaves. La llave pública va sin las líneas
--    -----BEGIN/END----- y en una sola línea.
-- -----------------------------------------------------------------------------
CREATE USER IF NOT EXISTS CENTINELA_SVC
  TYPE              = SERVICE
  DEFAULT_ROLE      = CENTINELA_ROLE
  DEFAULT_WAREHOUSE = CENTINELA_WH
  DEFAULT_NAMESPACE = CENTINELA.RAW
  COMMENT = 'Usuario de servicio de Kestra, dbt y Spark';

ALTER USER CENTINELA_SVC SET RSA_PUBLIC_KEY = '<PEGA_AQUI_LA_LLAVE_PUBLICA>';

GRANT ROLE CENTINELA_ROLE TO USER CENTINELA_SVC;

-- -----------------------------------------------------------------------------
-- 7. Verificación: copia estos resultados (no son secretos).
-- -----------------------------------------------------------------------------
-- Identificador de la cuenta para SNOWFLAKE_ACCOUNT en .env:
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS snowflake_account;

-- Huella de la llave pública registrada (RSA_PUBLIC_KEY_FP): debe coincidir con la local.
DESC USER CENTINELA_SVC;

SHOW GRANTS TO ROLE CENTINELA_ROLE;
SHOW RESOURCE MONITORS LIKE 'CENTINELA_RM';
