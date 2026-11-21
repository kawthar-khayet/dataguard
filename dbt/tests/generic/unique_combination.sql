{# Échoue si une combinaison de colonnes apparaît plusieurs fois. #}
{% test unique_combination(model, columns) %}
  select {{ columns | join(', ') }}, count(*) as n
  from {{ model }}
  group by {{ columns | join(', ') }}
  having count(*) > 1
{% endtest %}
