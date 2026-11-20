-- Vue de la table source.abonnements, telle que le rôle « analyst » a le droit de la voir.
{{ config(alias='abonnements') }}
{{ protected_select('abonnements', role='analyst') }}
