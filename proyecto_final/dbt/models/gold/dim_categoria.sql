-- Dimensión categoría de comercio (grocery_pos, shopping_net, ...).
-- El sufijo indica el canal: _pos = presencial, _net = en línea.
select
    md5(category)                                    as categoria_sk,
    category                                         as categoria,
    case
        when category like '%\\_net' escape '\\' then 'en_linea'
        when category like '%\\_pos' escape '\\' then 'presencial'
        else 'otro'
    end                                              as canal
from {{ ref('slv_transacciones') }}
group by category
