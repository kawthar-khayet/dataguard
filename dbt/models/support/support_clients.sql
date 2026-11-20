-- Vue de la table source.clients, telle que le rôle « support_client » a le droit de la voir.
{{ config(alias='clients') }}
{{ protected_select('clients', role='support_client') }}
