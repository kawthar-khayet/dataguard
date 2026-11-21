-- Vue de marts.fct_resiliations, telle que le rôle « analyst » a le droit de la voir.
{{ config(alias='fct_resiliations') }}
{{ protected_select(ref('fct_resiliations'), 'fct_resiliations', role='analyst') }}
