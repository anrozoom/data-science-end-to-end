{#
  Por defecto dbt concatena el esquema del perfil con el de cada carpeta
  (SILVER_BRONZE, SILVER_GOLD...). Aquí cada capa usa exactamente su esquema:
  BRONZE, SILVER o GOLD, los mismos que creó snowflake/01_setup.sql.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim | upper }}
    {%- endif -%}
{%- endmacro %}
