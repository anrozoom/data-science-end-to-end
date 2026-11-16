-- La limpieza quitó el prefijo artificial 'fraud_' de todos los comercios.
select trans_num, merchant
from {{ ref('slv_transacciones') }}
where startswith(merchant, 'fraud_')
