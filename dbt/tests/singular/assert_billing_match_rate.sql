-- Quelle part des factures a pu être rattachée à un client du CRM (via le téléphone) ?
-- Avertissement (pas une erreur) sous 95 % : la cause est souvent un téléphone
-- manquant ou mal saisi dans le CRM. À surveiller, pas à bloquer.
{{ config(severity='warn') }}

select
    count(*)                                              as nb_factures,
    count(client_id)                                      as nb_rattachees,
    round(100.0 * count(client_id) / count(*), 2)         as taux_pct
from {{ ref('fct_factures') }}
having 100.0 * count(client_id) / count(*) < 95
