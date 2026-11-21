-- Factures nettoyées : montants « 349,00 DH » → 349.00, deux formats de date,
-- IBAN sans espaces, et suppression des lignes exportées deux fois.
with numbered as (
    select *,
           row_number() over (partition by num_facture order by _source_file) as rn
    from {{ source('raw', 'factures') }}
)
select
    num_facture,
    {{ normalize_phone('msisdn') }}                         as telephone,
    {{ parse_amount('montant') }}                           as montant,
    {{ parse_date_multi('date_facture') }}                  as date_facture,
    mode_paiement,
    case when upper(iban) like 'MA%' then upper(replace(iban, ' ', '')) end   as iban,
    case when iban like '****%' then right(iban, 4) end    as carte_4_derniers,
    _source_file                                            as fichier_source
from numbered
where rn = 1
