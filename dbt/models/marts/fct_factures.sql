-- Factures rattachées à un client grâce au téléphone (la facturation ne connaît pas l'id CRM).
select
    f.num_facture,
    p.master_id                                  as client_id,     -- NULL si aucun client trouvé
    date_trunc('month', f.date_facture)::date    as mois,
    f.date_facture,
    f.montant,
    f.mode_paiement,
    f.iban,
    f.carte_4_derniers,
    f.fichier_source
from {{ ref('stg_factures') }} f
left join {{ ref('int_phone_to_client') }} p using (telephone)
