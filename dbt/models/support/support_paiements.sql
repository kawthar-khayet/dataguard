-- Vue de la table source.paiements, telle que le rôle « support_client » a le droit de la voir.
{{ config(alias='paiements') }}
{{ protected_select('paiements', role='support_client') }}
