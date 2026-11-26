-- El hecho tiene el mismo grano que SILVER: una fila por transacción, sin pérdidas
-- ni duplicados al construir las claves de las dimensiones.
select s.n as filas_silver, f.n as filas_fct
from (select count(*) as n from {{ ref('slv_transacciones') }}) s
cross join (select count(*) as n from {{ ref('fct_transacciones') }}) f
where s.n <> f.n
