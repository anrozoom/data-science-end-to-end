-- SILVER: capa de limpieza (la "staging" del enunciado). Cada decisión sale del
-- diagnóstico de calidad (docs/calidad_datos.md):
--   1. Deduplicación por trans_num: se conserva la carga más reciente.
--   2. merchant: se quita el prefijo artificial 'fraud_' de Sparkov (100 % de las filas).
--   3. zip: se completa con ceros a la izquierda hasta 5 dígitos (se perdieron al
--      exportar como número; afecta a estados del noreste de EE. UU.).
--   4. Tiempo del evento: trans_ts (texto original). unix_time NO se usa: está
--      desplazado ~2.556 días respecto de trans_ts en el generador.
--   5. Reglas de validez: monto > 0, coordenadas en rango, fechas parseables,
--      is_fraud en {0,1}. Las filas que no cumplen se excluyen (ver tests).
--   6. Derivadas sin fuga de información (solo usan la propia fila):
--      edad en la fecha de la transacción, hora, día de la semana, distancia
--      cliente-comercio y época en segundos para las ventanas de Spark.
with deduplicado as (
    select *
    from {{ ref('brz_transacciones') }}
    qualify row_number() over (
        partition by trans_num
        order by ingested_at desc, load_date desc
    ) = 1
),

valido as (
    select *
    from deduplicado
    where trans_ts is not null
      and amt > 0
      and lat between -90 and 90 and long between -180 and 180
      and merch_lat between -90 and 90 and merch_long between -180 and 180
      and dob is not null
      and is_fraud in (0, 1)
)

select
    trans_num,
    trans_ts,
    trans_ts::date                                           as trans_fecha,
    hour(trans_ts)                                           as trans_hora,
    dayofweekiso(trans_ts)                                   as trans_dia_semana,  -- 1 = lunes
    date_part(epoch_second, trans_ts)                        as trans_epoch,
    cc_num,
    regexp_replace(merchant, '^fraud_', '')                  as merchant,
    category,
    amt,
    first_name,
    last_name,
    gender,
    street,
    city,
    state,
    lpad(zip, 5, '0')                                        as zip,
    lat,
    long,
    city_pop,
    job,
    dob,
    datediff('year', dob, trans_ts)
        - iff(dateadd('year', datediff('year', dob, trans_ts), dob) > trans_ts::date, 1, 0)
                                                             as edad_en_transaccion,
    merch_lat,
    merch_long,
    haversine(lat, long, merch_lat, merch_long)              as distancia_km,
    is_fraud,
    source_file,
    load_date,
    ingested_at
from valido
