-- Vue de la table source.abonnements, telle que le rôle « support_client » a le droit de la voir.
{{ config(alias='abonnements') }}
{{ protected_select('abonnements', role='support_client') }}
