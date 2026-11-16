-- BRONZE es 1:1 con RAW: no puede ganar ni perder filas.
select r.n as filas_raw, b.n as filas_bronze
from (select count(*) as n from {{ source('raw', 'transacciones') }}) r
cross join (select count(*) as n from {{ ref('brz_transacciones') }}) b
where r.n <> b.n
