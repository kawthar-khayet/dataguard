-- Vue de la table source.reclamations, telle que le rôle « analyst » a le droit de la voir.
{{ config(alias='reclamations') }}
{{ protected_select('reclamations', role='analyst') }}
