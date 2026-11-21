-- Détail des appels. Les durées vides ou négatives (erreurs de collecte) deviennent NULL.
select
    {{ normalize_phone('msisdn_appelant') }}               as telephone_appelant,
    {{ normalize_phone('msisdn_appele') }}                 as telephone_appele,
    date_heure::timestamp                                  as date_heure,
    case when duree_sec ~ '^\d+$' then duree_sec::int end as duree_sec,
    cell_id,
    type
from {{ source('raw', 'cdr') }}
