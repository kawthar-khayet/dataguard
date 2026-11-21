-- Résiliations : profil du client parti, revenu perdu et ce qu'il a dit au centre d'appel.
with tickets as (
    select
        master_id,
        count(*)                                                  as nb_tickets,
        (array_agg(motif order by ouvert_le desc))[1]             as dernier_motif,
        (array_agg(notes order by ouvert_le desc))[1]             as derniere_note
    from {{ ref('int_tickets_clients') }}
    where master_id is not null
    group by master_id
),
revenus as (
    select client_id, sum(montant_total) as revenu_6_mois
    from {{ ref('fct_revenus_mensuels') }}
    group by client_id
)
select
    c.client_id,
    c.type_contrat,
    c.internet,
    c.mode_paiement,
    c.mensualite,
    c.date_debut,
    c.date_resiliation,
    (c.date_resiliation - c.date_debut) / 30          as anciennete_mois,
    coalesce(r.revenu_6_mois, 0)                      as revenu_6_mois,
    coalesce(t.nb_tickets, 0)                         as nb_tickets,
    t.dernier_motif,
    t.derniere_note
from {{ ref('dim_clients') }} c
left join tickets t on t.master_id = c.client_id
left join revenus r on r.client_id = c.client_id
where c.statut = 'résilié'
