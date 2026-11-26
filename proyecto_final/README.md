# Proyecto final · Centinela: detección de fraude con tarjeta, de punta a punta

> **Estado: en construcción (fase 0 de 8).** Este README se completa al final con el orden de ejecución completo desde cero.

Proyecto **Centinela**: puntuar cada transacción con tarjeta en el momento de la autorización y decidir **aprobar, verificar o retener**, en reemplazo de las reglas fijas del banco.

**Formulación → Pipeline de datos → OBT → Experimentación → Modelo registrado → API → Pruebas y CI/CD → Predicciones registradas → Monitoreo → Alertas → Reentrenamiento → Resultado de negocio → Presentación ejecutiva**

## Origen de cada parte

| Parte | Viene de | Estado en `proyecto_final/` |
|---|---|---|
| Ingesta (Kestra), dbt y Spark | `pset_2/` (tag `pset-02`) | Copiados. La ingesta se corrige en la fase 1 (observación del PSet 2) |
| `src/` y notebooks 01–05 | `pset_3/` (tag `pset-03`) | Copiados **con su salida guardada**; no se vuelven a ejecutar (ver `docs/cambios.md`) |
| Registro de modelos | MLflow del PSet 3 | Mismos volúmenes: `centinela-modelo` v1 `@champion` y v2 `@challenger` |

## Levantar la infraestructura (fase 0)

```bash
cd proyecto_final
cp .env.example .env && chmod 600 .env     # completar valores (ver .env.example)
bash scripts/generar_secretos_kestra.sh     # secretos de Kestra -> .env.kestra
docker compose up -d                        # Kestra :8080 · Spark UI :8081 · MLflow :5055
```

Si el MLflow del PSet 3 está corriendo, detenlo primero (`cd pset_3 && docker compose stop`): usa el mismo puerto y la misma base de datos.

**No uses `docker compose down -v`:** borraría los volúmenes de MLflow, que guardan el registro de modelos y todas las corridas.

## Snowflake

- **Cuenta en uso:** la original del PSet 2, con las mismas credenciales por par de llaves (`.env` y `secrets/snowflake_key.p8`, fuera de git). El esquema `PRODUCCION` del PSet 4 se crea una vez como ACCOUNTADMIN con [`snowflake/02_produccion.sql`](snowflake/02_produccion.sql).
- **Alternativa (cuenta nueva de respaldo):** si la cuenta original no está disponible, ejecuta [`snowflake/01_setup.sql`](snowflake/01_setup.sql) en la cuenta nueva (crea el warehouse, el resource monitor, los esquemas `RAW`…`OBT` y `PRODUCCION`, el rol y el usuario de servicio), genera un par de llaves nuevo y apunta `SNOWFLAKE_ACCOUNT` en `.env` a esa cuenta. Después reconstruye la OBT con la ingesta (fase 1) y verifica su equivalencia con `scripts/huella_obt.py` (referencia en `docs/obt_huella_referencia.json`).

## Documentación

- [`docs/cambios.md`](docs/cambios.md): observaciones de los PSet 1 a 3 y decisiones que cambian.
- `docs/datos/`: evidencia del pipeline de datos (PSet 2). `docs/eda/`, `docs/features/`, `docs/modelos/`, `docs/tuning/` y `docs/seleccion/`: evidencia de la experimentación (PSet 3).
- `docs/historial/`: memos de los PSet anteriores.
