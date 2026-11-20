{#
  Contrôle d'accès (RBAC) dans PostgreSQL.

  - analyst        : lit uniquement le schéma `analyst` (tout masqué)
  - support_client : lit uniquement le schéma `support` (Confidentiel en clair, Restreint masqué)
  - dpo            : lit les données sources en clair

  Les vues appartiennent à l'utilisateur dbt : un analyste peut lire la vue
  sans avoir aucun droit sur la table source qu'elle masque.
#}

{% macro create_roles() %}
  {% for role in ['analyst', 'support_client', 'dpo'] %}
    do $$ begin
      if not exists (select from pg_roles where rolname = '{{ role }}') then
        create role {{ role }} nologin;
      end if;
    end $$;
  {% endfor %}
{% endmacro %}

{# Copie le sel de hachage (variable d'environnement) dans une table que seul dbt peut lire. #}
{% macro store_hash_salt() %}
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
    primary key (table_name, column_name, text_hash)
  );
{% endmacro %}

{% macro grant_schema_usage() %}
  grant usage on schema analyst to analyst;
  grant usage on schema support to support_client;
  grant usage on schema source to dpo;
  grant select on all tables in schema source to dpo;
{% endmacro %}

{# Par défaut dbt nommerait le schéma « public_analyst » : on garde « analyst ». #}
{% macro generate_schema_name(custom_schema_name, node) %}
  {{ custom_schema_name if custom_schema_name else target.schema }}
{% endmacro %}
