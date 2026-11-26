-- Todo código postal queda con exactamente 5 dígitos.
select trans_num, zip
from {{ ref('slv_transacciones') }}
where not regexp_like(zip, '[0-9]{5}')
