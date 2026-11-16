-- Dimensión cliente: una fila por tarjeta (cc_num). El diagnóstico mostró que
-- nombre, dirección, ubicación, ocupación y fecha de nacimiento no cambian por
-- cc_num, así que son atributos estables de la dimensión (SCD tipo 1).
-- Nombres y direcciones son sintéticos: se conservan para trazabilidad, no como
-- variables del modelo.
select
    md5(cc_num)            as cliente_sk,
    cc_num,
    any_value(first_name)  as first_name,
    any_value(last_name)   as last_name,
    any_value(gender)      as gender,
    any_value(street)      as street,
    any_value(city)        as city,
    any_value(state)       as state,
    any_value(zip)         as zip,
    any_value(lat)         as lat,
    any_value(long)        as long,
    any_value(city_pop)    as city_pop,
    any_value(job)         as job,
    any_value(dob)         as dob,
    min(trans_ts)          as primera_transaccion,
    count(*)               as n_transacciones
from {{ ref('slv_transacciones') }}
group by cc_num
