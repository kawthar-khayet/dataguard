select
    btrim(id_client)                     as client_id,
    type_contrat,
    internet,
    telephonie = 'oui'                   as telephonie,
    nullif(options, '')                  as options,
    mode_paiement,
    mensualite::numeric(10, 2)           as mensualite,
    -- Vrai désordre du jeu IBM Telco : total vide pour les clients arrivés ce mois-ci
    -- (pas encore facturés). Ce n'est pas une valeur manquante : c'est 0.
    case when btrim(total_facture) = '' then 0
         else total_facture::numeric(10, 2) * 10 end   as total_facture,   -- dollars → dirhams
    date_debut::date                     as date_debut,
    statut,
    nullif(date_resiliation, '')::date   as date_resiliation
from {{ source('raw', 'crm_contrats') }}
