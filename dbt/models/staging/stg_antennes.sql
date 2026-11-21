-- Antennes OpenCelliD (Maroc). Données sous licence CC BY-SA 4.0 : voir ATTRIBUTION.md.
-- Vrai défaut de la source, détecté par le test unique : un même identifiant
-- (mcc-net-area-cell) peut apparaître avec deux technologies radio. On garde
-- la ligne la plus fiable, celle qui a le plus de mesures (samples).
select distinct on (cell_id)
    cell_id, radio, operateur_mnc, lat, lon, portee_m
from (
    select
        mcc || '-' || net || '-' || area || '-' || cell   as cell_id,
        radio,
        net::int                                          as operateur_mnc,
        lat::double precision                             as lat,
        lon::double precision                             as lon,
        range::int                                        as portee_m,
        samples::int                                      as samples
    from {{ source('raw', 'antennes') }}
) a
order by cell_id, samples desc
