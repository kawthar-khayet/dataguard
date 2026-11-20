{#
  Le cœur de la protection : génère le SELECT d'une table source pour un rôle donné.

  Pour chaque colonne de la table :
    - une politique APPROUVÉE existe, et le rôle n'est pas autorisé en clair → colonne masquée
    - sinon → colonne en clair

  Les politiques sont lues dans governance.policy AU MOMENT DU BUILD : quand un
  administrateur approuve une politique dans Streamlit, le prochain `dbt build`
  l'applique, sans modifier aucun fichier SQL.
#}

{% macro protected_select(table_name, role) %}
  {%- set src = source('source', table_name) -%}

  {%- if execute -%}
    {%- set columns = adapter.get_columns_in_relation(src) -%}
    {%- set policies = run_query(
          "select column_name, masking_method, array_to_string(clear_roles, ',') as clear_roles "
          ~ "from governance.policy where status = 'approuvée' and table_name = '" ~ table_name ~ "'") -%}
    {%- set rules = {} -%}
    {%- for p in policies.rows -%}
      {%- do rules.update({p['column_name']: p}) -%}
    {%- endfor -%}

    select
    {%- for c in columns %}
      {%- set p = rules.get(c.name) %}
      {%- if p and role not in p['clear_roles'].split(',') %}
      {{ mask(p['masking_method'], adapter.quote(c.name), table_name, c.name) }} as {{ adapter.quote(c.name) }}
      {%- else %}
      {{ adapter.quote(c.name) }}
      {%- endif %}{{ "," if not loop.last }}
    {%- endfor %}
    from {{ src }}
  {%- else -%}
    select * from {{ src }}
  {%- endif -%}
{% endmacro %}
