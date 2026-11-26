-- =============================================================================
-- Proyecto final · Centinela · Configuración de Snowflake para una CUENTA NUEVA (respaldo)
-- La entrega usa la cuenta original del PSet 2; ahí basta con snowflake/02_produccion.sql.
-- Ejecutar UNA vez en Snowsight (Projects > Worksheets) con el rol ACCOUNTADMIN.
-- Es idempotente: si se vuelve a correr, no duplica ni borra nada.
-- Antes de correrlo, reemplaza <PEGA_AQUI_LA_LLAVE_PUBLICA> en el bloque 6.
--
-- Igual que pset_2/snowflake/01_setup.sql, más el esquema PRODUCCION del PSet 4
-- (lotes de la simulación, PREDICCIONES, MONITOREO y ALERTAS).
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- 1. Warehouse XS: cómputo mínimo, se apaga a los 60 s sin uso; nace apagado.
CREATE WAREHOUSE IF NOT EXISTS CENTINELA_WH
  WAREHOUSE_SIZE      = 'XSMALL'
  AUTO_SUSPEND        = 60
  AUTO_RESUME         = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Centinela: ingesta, dbt, Spark, API y monitoreo';

-- 2. Resource monitor: tope de 15 créditos al mes (aviso 50 % y 75 %, SUSPEND 100 %,
--    SUSPEND_IMMEDIATE 110 %). La cuenta de prueba trae créditos de sobra; esto evita sustos.
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

-- 3. Base de datos y un esquema por capa, más PRODUCCION (PSet 4).
CREATE DATABASE IF NOT EXISTS CENTINELA COMMENT = 'Proyecto Centinela';
CREATE SCHEMA IF NOT EXISTS CENTINELA.RAW        COMMENT = 'Datos tal como llegan de Kaggle (Kestra)';
CREATE SCHEMA IF NOT EXISTS CENTINELA.BRONZE     COMMENT = 'Copia 1:1 de RAW con tipos y nombres normalizados (dbt)';
CREATE SCHEMA IF NOT EXISTS CENTINELA.SILVER     COMMENT = 'Datos limpios y deduplicados (dbt)';
CREATE SCHEMA IF NOT EXISTS CENTINELA.GOLD       COMMENT = 'Star schema (dbt)';
CREATE SCHEMA IF NOT EXISTS CENTINELA.OBT        COMMENT = 'One Big Table (Spark)';
CREATE SCHEMA IF NOT EXISTS CENTINELA.PRODUCCION COMMENT = 'Simulación de producción: lotes, PREDICCIONES, MONITOREO, ALERTAS (PSet 4)';

-- 4. Rol de servicio, colgado de SYSADMIN para que ACCOUNTADMIN vea lo que crea el pipeline.
CREATE ROLE IF NOT EXISTS CENTINELA_ROLE COMMENT = 'Rol de servicio del proyecto Centinela';
GRANT ROLE CENTINELA_ROLE TO ROLE SYSADMIN;

-- 5. Permisos mínimos. MODIFY solo sobre CENTINELA_WH (subir AUTO_SUSPEND durante el backfill).
GRANT USAGE, OPERATE, MODIFY ON WAREHOUSE CENTINELA_WH TO ROLE CENTINELA_ROLE;
GRANT USAGE ON DATABASE CENTINELA TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA CENTINELA.RAW        TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA CENTINELA.BRONZE     TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA CENTINELA.SILVER     TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA CENTINELA.GOLD       TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA CENTINELA.OBT        TO ROLE CENTINELA_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA CENTINELA.PRODUCCION TO ROLE CENTINELA_ROLE;
-- Lectura del consumo de créditos (solo lectura).
GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE CENTINELA_ROLE;

-- 6. Usuario de servicio: TYPE = SERVICE (sin contraseña ni Snowsight; solo par de llaves).
--    La llave pública va sin las líneas -----BEGIN/END----- y en una sola línea.
CREATE USER IF NOT EXISTS CENTINELA_SVC
  TYPE              = SERVICE
  DEFAULT_ROLE      = CENTINELA_ROLE
  DEFAULT_WAREHOUSE = CENTINELA_WH
  DEFAULT_NAMESPACE = CENTINELA.RAW
  COMMENT = 'Usuario de servicio de Kestra, dbt, Spark, la API y el monitoreo';
ALTER USER CENTINELA_SVC SET RSA_PUBLIC_KEY = '<PEGA_AQUI_LA_LLAVE_PUBLICA>';
GRANT ROLE CENTINELA_ROLE TO USER CENTINELA_SVC;

-- 7. Verificación (copia estos resultados; no son secretos).
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS snowflake_account;
DESC USER CENTINELA_SVC;                       -- RSA_PUBLIC_KEY_FP debe coincidir con la huella local
SHOW WAREHOUSES LIKE 'CENTINELA_WH';           -- columna resource_monitor = CENTINELA_RM
SHOW GRANTS TO ROLE CENTINELA_ROLE;
