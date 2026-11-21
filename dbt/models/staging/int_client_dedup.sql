-- Dédoublonnage : deux comptes CRM avec le même CIN sont la même personne.
-- Le compte le plus ancien devient le « maître » ; les autres y sont rattachés.
-- (Le nom ne suffit pas : il est saisi en majuscules, à l'envers, avec des espaces…)
select
    client_id,
    first_value(client_id) over (
        partition by coalesce(cin, client_id)      -- sans CIN, un compte reste seul
        order by date_creation, client_id
    ) as master_id
from {{ ref('stg_crm_clients') }}
