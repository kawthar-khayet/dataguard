-- Vue de marts.dim_clients, telle que le rôle « analyst » a le droit de la voir.
{{ config(alias='dim_clients') }}
{{ protected_select(ref('dim_clients'), 'dim_clients', role='analyst') }}
