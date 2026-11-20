{#
  Une macro par méthode de masquage. Chacune reçoit le nom d'une colonne
  et renvoie l'expression SQL qui la masque.
#}

{% macro mask(method, col, table_name, column_name) %}
  {%- if method == 'HASH' -%}
    -- SHA-256 + sel secret : même CIN → même code (jointures possibles), mais irréversible.
    -- Le sel est lu dans une table protégée, pas écrit dans la vue : la définition d'une vue
    -- est lisible par tous dans PostgreSQL (pg_views), le sel y serait exposé.
    encode(sha256(convert_to((select salt from governance.hash_salt) || {{ col }}::text, 'UTF8')), 'hex')
  {%- elif method == 'PARTIAL_LAST4' -%}
    -- MA************************1234
    left({{ col }}, 2) || repeat('*', greatest(length({{ col }}) - 6, 0)) || right({{ col }}, 4)
  {%- elif method == 'PARTIAL_PHONE' -%}
    -- on normalise d'abord (+212 6.. / 06 .. ..) en 0612345678, puis 06******78
    left('0' || right(regexp_replace({{ col }}, '[^0-9]', '', 'g'), 9), 2) || '******'
      || right(regexp_replace({{ col }}, '[^0-9]', '', 'g'), 2)
  {%- elif method == 'PARTIAL_EMAIL' -%}
    -- a***@domaine.ma
    left({{ col }}, 1) || '***@' || split_part({{ col }}, '@', 2)
  {%- elif method == 'YEAR_ONLY' -%}
    extract(year from {{ col }})::int
  {%- elif method == 'REDACT' -%}
    '[MASQUÉ]'::text
  {%- elif method == 'ANONYMIZE_TEXT' -%}
    -- Le NER (Presidio) ne tourne pas en SQL : le texte anonymisé est pré-calculé en Python
    -- et retrouvé ici grâce à l'empreinte md5 du texte original.
    coalesce(
      (select a.anonymized from governance.text_anonymized a
       where a.table_name = '{{ table_name }}' and a.column_name = '{{ column_name }}'
         and a.text_hash = md5({{ col }})),
      '[TEXTE NON ANONYMISÉ]')
  {%- else -%}
    {{ exceptions.raise_compiler_error("Méthode de masquage inconnue : " ~ method) }}
  {%- endif -%}
{% endmacro %}
