-- Dimensión comercio: una fila por comercio (merchant sin el prefijo 'fraud_').
-- La ubicación del comercio (merch_lat/long) cambia en CADA transacción en Sparkov,
-- por eso vive en el hecho y no aquí. La categoría tampoco: algunos comercios
-- aparecen con más de una, así que la categoría es su propia dimensión.
select
    md5(merchant)                        as comercio_sk,
    merchant                             as comercio,
    count(distinct category)             as n_categorias,
    count(distinct category) > 1         as es_multicategoria,
    count(*)                             as n_transacciones
from {{ ref('slv_transacciones') }}
group by merchant
