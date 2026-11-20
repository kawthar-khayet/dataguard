-- Vue de la table source.paiements, telle que le rôle « analyst » a le droit de la voir.
{{ config(alias='paiements') }}
{{ protected_select('paiements', role='analyst') }}
