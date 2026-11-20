-- Exécuté automatiquement par PostgreSQL au tout premier démarrage du conteneur.
-- Deux espaces séparés :
--   source     : les données "métier" de l'opérateur (clients, abonnements, paiements, réclamations)
--   governance : ce que DataGuard produit (catalogue des colonnes, politiques, historique)

CREATE SCHEMA IF NOT EXISTS source;
CREATE SCHEMA IF NOT EXISTS governance;
