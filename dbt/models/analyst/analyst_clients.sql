-- Vue de la table source.clients, telle que le rôle « analyst » a le droit de la voir.
{{ config(alias='clients') }}
{{ protected_select('clients', role='analyst') }}
