-- Trafic par antenne en novembre.
-- Protection de la vie privée : une antenne utilisée par moins de 5 abonnés distincts
-- n'est pas publiée (k-anonymat, k = 5) — sinon on pourrait deviner où se trouve
-- une personne précise.
select
    a.cell_id,
    a.radio,
    a.operateur_mnc,
    a.lat,
    a.lon,
    count(*)                                        as nb_evenements,
    count(*) filter (where c.type = 'voix')         as nb_appels,
    round(sum(c.duree_sec) / 60.0, 1)               as minutes,
    count(distinct c.telephone_appelant)            as nb_abonnes_distincts
from {{ ref('stg_cdr') }} c
join {{ ref('stg_antennes') }} a using (cell_id)
group by a.cell_id, a.radio, a.operateur_mnc, a.lat, a.lon
having count(distinct c.telephone_appelant) >= 5
