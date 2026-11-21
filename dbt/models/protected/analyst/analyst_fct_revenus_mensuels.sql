-- Vue de marts.fct_revenus_mensuels, telle que le rôle « analyst » a le droit de la voir.
{{ config(alias='fct_revenus_mensuels') }}
{{ protected_select(ref('fct_revenus_mensuels'), 'fct_revenus_mensuels', role='analyst') }}
