-- Table de correspondance téléphone → client maître.
-- C'est la clé qui relie les systèmes : la facturation et le centre d'appel
-- ne connaissent souvent que le numéro, pas l'identifiant CRM.
select
    c.telephone,
    min(d.master_id) as master_id
from {{ ref('stg_crm_clients') }} c
join {{ ref('int_client_dedup') }} d using (client_id)
where c.telephone is not null
group by c.telephone
