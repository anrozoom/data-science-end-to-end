-- Regla de negocio: la fuente cubre del 2019-01-01 al 2020-12-31.
select trans_num, trans_ts
from {{ ref('slv_transacciones') }}
where trans_ts < '2019-01-01' or trans_ts >= '2021-01-01'
