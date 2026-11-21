-- Le dédoublonnage retrouve-t-il les vrais doublons ?
-- La vérité vient du générateur (governance.ground_truth_dups).
-- Renvoie chaque doublon mal rattaché → 0 ligne = 100 % retrouvés.
select
    t.dup_id,
    t.master_id   as maitre_attendu,
    d.master_id   as maitre_calcule
from {{ source('governance', 'ground_truth_dups') }} t
left join {{ ref('int_client_dedup') }} d on d.client_id = t.dup_id
where d.master_id is distinct from t.master_id
