-- =============================================================================
-- Proyecto final · Centinela · Esquema PRODUCCION en la cuenta ORIGINAL (la del PSet 2)
-- Ejecutar UNA vez en Snowsight con el rol ACCOUNTADMIN. Idempotente.
-- (En una cuenta nueva no hace falta: snowflake/01_setup.sql ya lo incluye.)
-- =============================================================================
USE ROLE ACCOUNTADMIN;
CREATE SCHEMA IF NOT EXISTS CENTINELA.PRODUCCION
  COMMENT = 'Simulación de producción: lotes, PREDICCIONES, MONITOREO, ALERTAS (PSet 4)';
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON SCHEMA CENTINELA.PRODUCCION TO ROLE CENTINELA_ROLE;
SHOW GRANTS ON SCHEMA CENTINELA.PRODUCCION;
