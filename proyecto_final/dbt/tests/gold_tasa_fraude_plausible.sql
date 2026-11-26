-- Regla del problema de negocio: el fraude es un evento raro. Si la tasa sale de
-- 0,1 %-2 %, algo se rompió en la carga o en los joins (p. ej., etiquetas perdidas).
select avg(is_fraud) as tasa_fraude
from {{ ref('fct_transacciones') }}
having avg(is_fraud) not between 0.001 and 0.02
