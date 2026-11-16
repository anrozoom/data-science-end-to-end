-- BRONZE: copia 1:1 de RAW con tipos correctos y nombres normalizados.
-- Sin reglas de negocio: no filtra, no deduplica, no corrige valores.
-- Mismo número de filas que RAW (lo verifica tests/bronze_conteo_igual_a_raw.sql).
select
    indice_origen::number                                        as indice_origen,
    to_timestamp_ntz(trans_date_trans_time, 'YYYY-MM-DD HH24:MI:SS') as trans_ts,
    cc_num::varchar                                              as cc_num,
    merchant::varchar                                            as merchant,
    category::varchar                                            as category,
    amt::number(12, 2)                                           as amt,
    first::varchar                                               as first_name,
    last::varchar                                                as last_name,
    gender::varchar                                              as gender,
    street::varchar                                              as street,
    city::varchar                                                as city,
    state::varchar                                               as state,
    zip::varchar                                                 as zip,
    lat::float                                                   as lat,
    long::float                                                  as long,
    city_pop::number                                             as city_pop,
    job::varchar                                                 as job,
    to_date(dob, 'YYYY-MM-DD')                                   as dob,
    trans_num::varchar                                           as trans_num,
    unix_time::number                                            as unix_time,
    merch_lat::float                                             as merch_lat,
    merch_long::float                                            as merch_long,
    is_fraud::number(1, 0)                                       as is_fraud,
    _source_file                                                 as source_file,
    _load_date                                                   as load_date,
    _ingested_at                                                 as ingested_at
from {{ source('raw', 'transacciones') }}
