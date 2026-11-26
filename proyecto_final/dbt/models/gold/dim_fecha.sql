-- Dimensión fecha: calendario completo 2019-01-01 a 2020-12-31 (731 días),
-- incluso los días sin transacciones (2020-02-29 no tiene datos en la fuente).
-- Incluye la partición temporal del PSet 1: entrenamiento hasta jun-2020, prueba desde jul-2020.
with calendario as (
    -- row_number y no seq4() directo: seq4 no garantiza una secuencia sin huecos.
    select dateadd('day', row_number() over (order by seq4()) - 1, '2019-01-01'::date) as fecha
    from table(generator(rowcount => 731))
)
select
    to_number(to_char(fecha, 'YYYYMMDD'))               as fecha_sk,
    fecha,
    year(fecha)                                         as anio,
    quarter(fecha)                                      as trimestre,
    month(fecha)                                        as mes,
    day(fecha)                                          as dia,
    dayofweekiso(fecha)                                 as dia_semana,       -- 1 = lunes
    dayofweekiso(fecha) in (6, 7)                       as es_fin_de_semana,
    iff(fecha < '2020-07-01', 'entrenamiento', 'prueba') as particion_temporal
from calendario
