-- SILVER conserva exactamente una fila por trans_num válido de BRONZE: la limpieza
-- solo puede quitar duplicados y filas que violan reglas de validez, nunca otras.
with b as (
    select count(distinct trans_num) as n_distintos,
           count(distinct iff(trans_ts is not null and amt > 0
                              and lat between -90 and 90 and long between -180 and 180
                              and merch_lat between -90 and 90 and merch_long between -180 and 180
                              and dob is not null and is_fraud in (0, 1), trans_num, null)) as n_validos
    from {{ ref('brz_transacciones') }}
),
s as (select count(*) as n from {{ ref('slv_transacciones') }})
select b.n_distintos, b.n_validos, s.n as filas_silver
from b cross join s
where s.n <> b.n_validos
