{#
  Le cœur de la protection : génère le SELECT d'un mart pour un rôle donné.

  Pour chaque colonne du mart :
    - une politique APPROUVÉE ou EN ATTENTE existe, et le rôle n'est pas autorisé
      en clair → colonne masquée
    - politique REJETÉE (un humain a dit « pas une donnée personnelle ») ou aucune → en clair

  Protection par défaut (« privacy by default ») : tant qu'un humain n'a pas décidé,
  on masque. Seul un REJET explicite peut remettre une colonne en clair.

  Les politiques sont lues dans governance.policy AU MOMENT DU BUILD : une décision
  prise dans Streamlit est appliquée au prochain build, sans modifier aucun fichier SQL.

  relation  : ref('dim_clients')       (le mart à protéger)
  mart_name : 'dim_clients'            (son nom dans le catalogue : marts.dim_clients)
#}

{% macro protected_select(relation, mart_name, role) %}
  {%- set table_name = 'marts.' ~ mart_name -%}

  {%- if execute -%}
    {%- set columns = adapter.get_columns_in_relation(relation) -%}
    {%- set policies = run_query(
          "select column_name, masking_method, array_to_string(clear_roles, ',') as clear_roles "
          ~ "from governance.policy where status in ('approuvée', 'proposée') "
          ~ "and table_name = '" ~ table_name ~ "'") -%}
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
    from {{ relation }}
  {%- else -%}
    select * from {{ relation }}
  {%- endif -%}
{% endmacro %}
