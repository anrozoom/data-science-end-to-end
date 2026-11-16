{#
  Test genérico de regla de negocio: falla con cada fila cuyo valor está fuera de
  [minimo, maximo]. Uso en schema.yml:
      - valor_entre:
          arguments: {minimo: 0, maximo: 100}
#}
{% test valor_entre(model, column_name, minimo, maximo) %}
select *
from {{ model }}
where {{ column_name }} < {{ minimo }}
   or {{ column_name }} > {{ maximo }}
{% endtest %}
