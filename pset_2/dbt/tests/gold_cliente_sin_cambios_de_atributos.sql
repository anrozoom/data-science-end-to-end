-- Supuesto del star schema: los atributos de dim_cliente son estables por cc_num.
-- Si un cliente aparece con más de una dirección o fecha de nacimiento, any_value()
-- estaría escondiendo un cambio y la dimensión necesitaría historia (SCD tipo 2).
select cc_num
from {{ ref('slv_transacciones') }}
group by cc_num
having count(distinct dob) > 1
    or count(distinct street || city || state || zip) > 1
    or count(distinct lat || ',' || long) > 1
