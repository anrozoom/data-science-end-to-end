-- Dimensión hora del día (0-23), con la franja nocturna que usa la regla fija
-- actual del banco (22:00 a 04:00, baseline del PSet 1).
with horas as (
    select row_number() over (order by seq4()) - 1 as hora from table(generator(rowcount => 24))
)
select
    hora                                   as hora_sk,
    hora,
    hora >= 22 or hora < 4                 as es_nocturna,
    case
        when hora < 6 then 'madrugada'
        when hora < 12 then 'manana'
        when hora < 18 then 'tarde'
        else 'noche'
    end                                    as franja
from horas
