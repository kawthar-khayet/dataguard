-- Tickets du centre d'appel. 10 % n'ont pas d'identifiant client :
-- ils sont rattachés par le téléphone dans int_tickets_clients.
select
    ticket_id,
    ouvert_le::timestamp                     as ouvert_le,
    canal,
    {{ clean_text('client_id') }}            as client_id,
    {{ normalize_phone('client_tel') }}      as telephone,
    motif,
    notes,
    agent_matricule
from {{ source('raw', 'tickets') }}
