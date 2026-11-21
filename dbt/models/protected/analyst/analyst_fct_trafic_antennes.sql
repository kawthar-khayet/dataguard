-- Vue de marts.fct_trafic_antennes, telle que le rôle « analyst » a le droit de la voir.
{{ config(alias='fct_trafic_antennes') }}
{{ protected_select(ref('fct_trafic_antennes'), 'fct_trafic_antennes', role='analyst') }}
