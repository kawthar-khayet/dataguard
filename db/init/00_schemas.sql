-- Exécuté automatiquement par PostgreSQL au tout premier démarrage du conteneur.
-- Les autres schémas sont créés par le pipeline :
--   crm                         generator/sources.py   (base du CRM simulé)
--   raw                         ingestion/load_raw.py  (données brutes)
--   staging, marts, ref         dbt                    (nettoyage, tables métier)
--   analyst, support            dbt                    (vues protégées par rôle)
--   governance                  ici                    (catalogue, politiques, historique de DataGuard)

CREATE SCHEMA IF NOT EXISTS governance;
