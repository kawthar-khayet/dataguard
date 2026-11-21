-- Rattache chaque ticket à un client maître : par l'identifiant s'il existe, sinon par le téléphone.
select
    t.*,
    coalesce(d.master_id, p.master_id)                       as master_id,
    case when d.master_id is not null then 'identifiant'
         when p.master_id is not null then 'téléphone' end   as rattache_par
from {{ ref('stg_tickets') }} t
left join {{ ref('int_client_dedup') }} d on d.client_id = t.client_id
left join {{ ref('int_phone_to_client') }} p on p.telephone = t.telephone
