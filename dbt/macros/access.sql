{#
  Contrôle d'accès (RBAC) dans PostgreSQL.

  | rôle           | lit                                   | voit                                   |
  |----------------|---------------------------------------|----------------------------------------|
  | analyst        | schéma analyst                        | tout masqué                            |
  | support_client | schéma support                        | « Confidentiel » en clair              |
  | data_engineer  | crm, raw, staging, marts              | tout (pour construire les pipelines)   |
  | dpo            | tout                                  | tout                                   |

  Les couches techniques (crm, raw, staging) ne sont JAMAIS ouvertes aux analystes.
  Les vues protégées appartiennent à l'utilisateur dbt : un analyste peut les lire
  sans avoir aucun droit sur les tables qu'elles masquent.
#}

{% macro create_roles() %}
  {% for role in ['analyst', 'support_client', 'data_engineer', 'dpo'] %}
    do $$ begin
      if not exists (select from pg_roles where rolname = '{{ role }}') then
        create role {{ role }} nologin;
      end if;
    end $$;
  {% endfor %}
{% endmacro %}

{# Copie le sel de hachage (variable d'environnement) dans une table que seul dbt peut lire. #}
{% macro store_hash_salt() %}
  create schema if not exists governance;
  create table if not exists governance.hash_salt (salt text not null);
  delete from governance.hash_salt;
  insert into governance.hash_salt values ('{{ env_var("DATAGUARD_HASH_SALT") }}');
{% endmacro %}

{# Table remplie par scanner/anonymize.py (texte libre anonymisé par Presidio). #}
{% macro create_text_anonymized() %}
  create table if not exists governance.text_anonymized (
    table_name  text,
    column_name text,
    text_hash   text,      -- md5 du texte original : sert uniquement à retrouver la ligne
    anonymized  text,
    version     int default 1,
    primary key (table_name, column_name, text_hash)
  );
{% endmacro %}

{# Droits par schéma. Un schéma pas encore créé (ex. analyst avant la phase protected) est ignoré. #}
{% macro grant_access() %}
  {% set grants = {
      'analyst':        ['analyst'],
      'support':        ['support_client'],
      'crm':            ['data_engineer', 'dpo'],
      'raw':            ['data_engineer', 'dpo'],
      'staging':        ['data_engineer', 'dpo'],
      'marts':          ['data_engineer', 'dpo'],
      'ref':            ['data_engineer', 'dpo'],
  } %}
  do $$ begin
  {% for schema, roles in grants.items() %}
    if exists (select from pg_namespace where nspname = '{{ schema }}') then
      {% for role in roles %}
      execute 'grant usage on schema {{ schema }} to {{ role }}';
      execute 'grant select on all tables in schema {{ schema }} to {{ role }}';
      {% endfor %}
    end if;
  {% endfor %}
  end $$;
{% endmacro %}

{# Par défaut dbt nommerait le schéma « public_analyst » : on garde « analyst ». #}
{% macro generate_schema_name(custom_schema_name, node) %}
  {{ custom_schema_name if custom_schema_name else target.schema }}
{% endmacro %}
