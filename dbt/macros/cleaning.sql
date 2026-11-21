{# Macros de nettoyage, réutilisées par tous les modèles staging. #}

{# Valeurs « vides déguisées » saisies par les agents → NULL #}
{% macro clean_text(col) -%}
  case when lower(btrim({{ col }})) in ('', 'n/a', 'na', 'inconnu', '-', 'null', 'none') then null
       else btrim({{ col }}) end
{%- endmacro %}

{# Téléphone marocain sous toutes ses formes → 0612345678 (sinon NULL) #}
{% macro normalize_phone(col) -%}
  case when regexp_replace({{ col }}, '[^0-9]', '', 'g') ~ '^(212|0)?[5-7][0-9]{8}$'
       then '0' || right(regexp_replace({{ col }}, '[^0-9]', '', 'g'), 9) end
{%- endmacro %}

{#
  Dates saisies dans 3 formats. Piège : avec une année sur 2 chiffres, PostgreSQL
  interprète « 47 » comme 2047. Une date de naissance dans le futur est donc
  ramenée au siècle précédent.
#}
{% macro parse_date_multi(col) -%}
  case
    when {{ col }} ~ '^\d{4}-\d{2}-\d{2}' then to_date(left({{ col }}, 10), 'YYYY-MM-DD')
    when {{ col }} ~ '^\d{2}/\d{2}/\d{4}$' then to_date({{ col }}, 'DD/MM/YYYY')
    when {{ col }} ~ '^\d{2}-\d{2}-\d{2}$' then
      case when to_date({{ col }}, 'DD-MM-YY') > current_date
           then (to_date({{ col }}, 'DD-MM-YY') - interval '100 years')::date
           else to_date({{ col }}, 'DD-MM-YY') end
  end
{%- endmacro %}

{# Accents cassés par un mauvais encodage (UTF-8 relu en Latin-1) : « FÃ¨s » → « Fès » #}
{% macro fix_mojibake(col) -%}
  replace(replace(replace(replace({{ col }}, 'Ã¨', 'è'), 'Ã©', 'é'), 'Ã§', 'ç'), 'Ã ', 'à')
{%- endmacro %}

{# « 349,00 DH » → 349.00 #}
{% macro parse_amount(col) -%}
  nullif(regexp_replace(replace({{ clean_text(col) }}, ',', '.'), '[^0-9.]', '', 'g'), '')::numeric(10, 2)
{%- endmacro %}
