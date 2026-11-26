-- Hecho de transacciones. GRANO: una fila por transacción (trans_num).
-- Medidas: monto y distancia cliente-comercio. Atributos propios de la transacción
-- que cambian en cada fila (ubicación del comercio, edad del titular en ese momento)
-- se quedan en el hecho. Target: is_fraud.
select
    t.trans_num,
    to_number(to_char(t.trans_fecha, 'YYYYMMDD'))  as fecha_sk,
    t.trans_hora                                   as hora_sk,
    md5(t.cc_num)                                  as cliente_sk,
    md5(t.merchant)                                as comercio_sk,
    md5(t.category)                                as categoria_sk,
    t.trans_ts,
    t.trans_epoch,
    t.amt,
    t.merch_lat,
    t.merch_long,
    t.distancia_km,
    t.edad_en_transaccion,
    t.edad_en_transaccion < 18                     as es_menor_de_edad,
    t.is_fraud,
    t.source_file
from {{ ref('slv_transacciones') }} t
