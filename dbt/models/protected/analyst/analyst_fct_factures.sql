-- Vue de marts.fct_factures, telle que le rôle « analyst » a le droit de la voir.
{{ config(alias='fct_factures') }}
{{ protected_select(ref('fct_factures'), 'fct_factures', role='analyst') }}
