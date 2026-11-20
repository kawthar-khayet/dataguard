# Données externes

Ces fichiers ne sont **pas** dans le dépôt Git : chacun les télécharge lui-même,
avec son propre compte, en respectant la licence de chaque source.
Le `.gitignore` empêche de les commiter par erreur.

| Dossier | Source | Licence | Rôle dans DataGuard |
|---|---|---|---|
| `telco/` | IBM Telco Customer Churn (Kaggle) | « Data files © Original Authors » : usage local uniquement, **ne pas redistribuer** | Comportement métier réel : abonnements, services, factures, résiliations |
| `opencellid/` | OpenCelliD | CC BY-SA 4.0 | Positions réelles des antennes mobiles au Maroc, pour des CDR réalistes |
| `piilo/` | PIILO (The Learning Agency) | CC BY 4.0 | Textes réels annotés, pour mesurer la détection NLP sur du vrai texte |

## 1. Telco Customer Churn

1. Se connecter sur Kaggle.
2. Ouvrir https://www.kaggle.com/datasets/blastchar/telco-customer-churn et cliquer sur **Download**.
3. Dézipper et placer le CSV dans `data/external/telco/`.
   Nom attendu : `WA_Fn-UseC_-Telco-Customer-Churn.csv`

## 2. OpenCelliD (Maroc, MCC 604)

1. Créer un compte sur https://opencellid.org/ et récupérer son **jeton d'accès (API token)**.
   Le jeton est personnel : ne jamais le mettre dans le code ni sur Git.
2. Sur https://opencellid.org/downloads.php, saisir le jeton puis cliquer sur **Show files**.
3. Télécharger l'export du **Maroc** (code pays MCC 604) s'il est proposé.
   Limite : 2 téléchargements par fichier et par jour.
4. Placer le fichier (`.csv.gz` ou `.csv`) dans `data/external/opencellid/`.

Colonnes attendues : `radio, mcc, net, area, cell, unit, lon, lat, range, samples, changeable, created, updated, averageSignal`

## 3. PIILO

1. Se connecter sur Kaggle.
2. Ouvrir https://www.kaggle.com/datasets/lburleigh/piilo-dataset et cliquer sur **Download**.
3. Dézipper et placer **tout le contenu** dans `data/external/piilo/`.

Les textes sont très probablement en anglais : pour cette évaluation, on utilisera un modèle spaCy anglais.
