{#
  Test de conformité : aucune donnée personnelle EN CLAIR ne doit apparaître dans une vue protégée.

  Il cherche les formats CIN / téléphone / IBAN / e-mail dans TOUTES les colonnes de la vue,
  y compris celles que le scanner a jugées non sensibles. C'est un filet de sécurité
  indépendant du scanner : si une PII a été oubliée, le build échoue quand même.

  Seules les colonnes dont un administrateur a REJETÉ la politique sont ignorées
  (ex. code_offre : décision humaine « ce n'est pas une PII »).

  Le test renvoie une ligne par colonne en fuite → 0 ligne = test réussi.
#}

{% test no_pii_leak(model, forbidden) %}
  {%- set patterns = {
      'CIN':   '(^|[^A-Za-z0-9])[A-Z]{1,2}[0-9]{5,6}([^A-Za-z0-9]|$)',
      'PHONE': '(^|[^0-9+])([+]212|0)[5-7]( ?[0-9]){8}([^0-9]|$)',
      'IBAN':  'MA[0-9]{26}',
      'EMAIL': '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}',
      'PERSON_AR': '[؀-ۿ]+[[:space:]]+[؀-ۿ]+',
  } -%}

  {%- if execute -%}
    {%- set table_name = model.identifier -%}
    {%- set rejected = run_query(
          "select column_name from governance.policy where status = 'rejetée' "
          ~ "and table_name = '" ~ table_name ~ "'").columns[0].values() -%}
    {%- set columns = adapter.get_columns_in_relation(model) | rejectattr('name', 'in', rejected) | list -%}
  {%- else -%}
    {%- set columns = [] -%}
  {%- endif -%}

  select colonne, type_pii, count(*) as lignes_en_clair
  from (
    {%- for c in columns %}
      {%- set outer = loop %}
      {%- for t in forbidden %}
    select '{{ c.name }}' as colonne, '{{ t }}' as type_pii
    from {{ model }} where {{ adapter.quote(c.name) }}::text ~ '{{ patterns[t] }}'
    {{ "union all" if not (outer.last and loop.last) }}
      {%- endfor %}
    {%- endfor %}
    {%- if not columns %} select null::text as colonne, null::text as type_pii where false {%- endif %}
  ) fuites
  group by colonne, type_pii
{% endtest %}
