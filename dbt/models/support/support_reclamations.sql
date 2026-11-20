-- Vue de la table source.reclamations, telle que le rôle « support_client » a le droit de la voir.
{{ config(alias='reclamations') }}
{{ protected_select('reclamations', role='support_client') }}
