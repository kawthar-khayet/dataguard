-- Chiffre d'affaires par client et par mois (aucune donnée personnelle).
select
    client_id,
    mois,
    sum(montant)   as montant_total,
    count(*)       as nb_factures
from {{ ref('fct_factures') }}
where client_id is not null
group by client_id, mois
