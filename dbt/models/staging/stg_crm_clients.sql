-- Clients du CRM nettoyés : un format unique par colonne, les « N/A » deviennent NULL.
-- Les doublons sont encore là : ils sont résolus dans int_client_dedup.
with src as (
    select * from {{ source('raw', 'crm_clients') }}
)
select
    btrim(src.id_client)                                                  as client_id,
    initcap(regexp_replace(btrim(src.nom_complet), '\s+', ' ', 'g'))      as nom_complet,
    upper(regexp_replace({{ clean_text('src.cin') }}, '\s', '', 'g'))     as cin,
    {{ normalize_phone(clean_text('src.tel')) }}                          as telephone,
    lower({{ clean_text('src.email') }})                                  as email,
    {{ parse_date_multi(clean_text('src.date_naiss')) }}                  as date_naissance,
    {{ clean_text('src.adresse') }}                                       as adresse,
    v.ville,
    case upper(left(btrim(src.genre), 1)) when 'F' then 'F' when 'M' then 'M' when 'H' then 'M' end as genre,
    src.date_creation::date                                               as date_creation
from src
left join {{ ref('villes_normalisation') }} v
    on v.variante = lower(btrim({{ fix_mojibake('src.ville') }}))
