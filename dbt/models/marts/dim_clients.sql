-- Vue client unifiée : UNE ligne par personne réelle, même si elle a plusieurs comptes CRM.
-- Les informations du compte maître sont prioritaires ; si elles manquent (ex. e-mail « N/A »),
-- on les complète avec celles des comptes en double.
with comptes as (
    select c.*, d.master_id, (c.client_id = d.master_id) as est_maitre
    from {{ ref('stg_crm_clients') }} c
    join {{ ref('int_client_dedup') }} d using (client_id)
),

personnes as (
    select
        master_id                                                                as client_id,
        max(nom_complet) filter (where est_maitre)                               as nom_complet,
        max(cin)                                                                 as cin,
        coalesce(max(telephone) filter (where est_maitre), max(telephone))       as telephone,
        coalesce(max(email) filter (where est_maitre), max(email))               as email,
        coalesce(max(date_naissance) filter (where est_maitre), max(date_naissance)) as date_naissance,
        coalesce(max(adresse) filter (where est_maitre), max(adresse))           as adresse,
        coalesce(max(ville) filter (where est_maitre), max(ville))               as ville,
        max(genre) filter (where est_maitre)                                     as genre,
        min(date_creation)                                                       as date_creation,
        count(*)                                                                 as nb_comptes_crm
    from comptes
    group by master_id
)

select
    p.*,
    k.type_contrat,
    k.internet,
    k.telephonie,
    k.options,
    k.mode_paiement,
    k.mensualite,
    k.statut,
    k.date_debut,
    k.date_resiliation
from personnes p
left join {{ ref('stg_crm_contrats') }} k on k.client_id = p.client_id
