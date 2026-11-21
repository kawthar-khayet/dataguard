# DataGuard

Détection, classification et protection automatiques des données personnelles
sur la plateforme data d'un opérateur télécom, de la source brute jusqu'aux tables métier
(contexte loi 09-08 / CNDP).

## Le scénario

Un opérateur dont les systèmes ont grandi séparément, avec le désordre que cela implique :

| Système | Format | Désordre |
|---|---|---|
| CRM | PostgreSQL (`crm`) | 5 % de doublons, téléphones et dates dans plusieurs formats, « N/A », villes mal orthographiées, accents cassés |
| Facturation | Exports CSV mensuels | Séparateur `;`, montants `349,00 DH`, un export en encodage Windows, lignes exportées deux fois, client identifié par son **téléphone** |
| Réseau | CSV de CDR (détail des appels) | Numéros au format `2126…`, durées vides ou négatives |
| Centre d'appel | JSON imbriqué | 10 % de tickets sans identifiant client, notes en texte libre contenant des données personnelles |
| Sauvegarde oubliée | `crm.clients_backup_2019` | Copie de 2019 pleine de données personnelles, que personne ne surveille |

**Données réelles** : comportement des clients (IBM Telco Customer Churn) et antennes mobiles du Maroc (OpenCelliD).
**Données synthétiques** : toutes les données personnelles. Voir [ATTRIBUTION.md](ATTRIBUTION.md) et [data/external/README.md](data/external/README.md).

## Le pipeline

```
sources ──► ingestion ──► raw ──► dbt staging ──► dbt marts
                                                     │
          scanner (crm, raw, staging, marts) ──► catalogue ──► politiques
                                                     │
                     validation humaine (Streamlit) ──► protection : vues masquées par rôle
```

| Étape | Ce qu'elle fait |
|---|---|
| `sources` | Simule les 5 systèmes à partir des données réelles ([generator/sources.py](generator/sources.py)) |
| `ingest` | Charge tout **tel quel** dans `raw` (tout en texte, + fichier d'origine et date de chargement) |
| `transform` | dbt **staging** : nettoyage, formats uniques, dédoublonnage par CIN, rattachement facturation ↔ CRM par téléphone. dbt **marts** : vue client unifiée, factures, revenus, trafic par antenne (k-anonymat), résiliations. 48 tests. |
| `scan` | Découverte → détection (regex + NLP + règles de contexte) → catalogue avec historique → proposition de politiques |
| validation | Un administrateur approuve ou rejette chaque politique |
| `protect` | Anonymisation du texte libre, vues masquées `analyst` et `support`, tests de non-fuite, contrôle des droits |

## Installation

```powershell
Copy-Item .env.example .env
docker compose up -d
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Télécharger ensuite les données externes : voir [data/external/README.md](data/external/README.md).

## Utilisation

```powershell
# 1. sources → ingestion → dbt (staging + marts) → scan
.\.venv\Scripts\python.exe -W ignore -m pipeline.run all

# 2. Valider les politiques (http://localhost:8501)
.\.venv\Scripts\streamlit.exe run app\app.py

# 3. Appliquer la protection
.\.venv\Scripts\python.exe -W ignore -m pipeline.run protect

# (optionnel) Mesurer le scanner sur la vérité terrain
.\.venv\Scripts\python.exe -W ignore -m scanner.evaluate
```

Chaque étape peut aussi être lancée seule : `pipeline.run ingest`, `pipeline.run transform`…

## Protection

**Selon la couche :**
- `crm`, `raw`, `staging` (couches techniques) → **restriction d'accès** : seuls `data_engineer` et `dpo` y accèdent.
- `marts` (couche exposée) → **masquage** colonne par colonne, dans des vues par rôle.

**Protection par défaut** : tant qu'une politique n'a pas été validée, la colonne est masquée. Seul un rejet explicite par un humain la remet en clair.

| Rôle | Lit | Voit |
|---|---|---|
| `analyst` | `analyst.*` | tout masqué |
| `support_client` | `support.*` | « Confidentiel » en clair (nom, téléphone, e-mail), « Restreint » masqué (CIN, IBAN) |
| `data_engineer` | `crm`, `raw`, `staging`, `marts` | tout, pour construire les pipelines |
| `dpo` | tout | tout |

| Type | Méthode | Exemple |
|---|---|---|
| CIN | Hachage SHA-256 avec sel secret | `73ac5791…` (les jointures restent possibles) |
| IBAN | 4 derniers chiffres | `MA**********************8065` |
| Téléphone | Préfixe + 2 derniers chiffres | `07******70` |
| E-mail | 1re lettre + domaine | `p***@club-internet.fr` |
| Nom, adresse | Suppression | `[MASQUÉ]` |
| Date de naissance | Année seule | `1975` |
| Texte libre | Anonymisation NLP | `<PERSON> (CIN <CIN>) appelle pour des coupures… Rappeler au <PHONE>.` |

## Résultats mesurés

- **Scanner** : 199 colonnes sur 4 couches, 46 PII sur 46 trouvées, 0 faux positif, 2 cas envoyés en validation humaine (`scanner.evaluate`).
- **Dédoublonnage** : 7 395 comptes CRM → 7 043 personnes ; les 352 doublons correspondent exactement à la vérité (test dbt).
- **Rattachement** des factures au CRM par téléphone : 98,2 %.

## Limites connues

- Les scores sont mesurés sur des données personnelles synthétiques : sur des données réelles, ils seraient plus bas. C'est pour ça que les cas incertains passent en validation humaine.
- Le modèle NER français reconnaît mal les noms en arabe au milieu d'une phrase (règle de prudence ajoutée) et les noms écrits tout en majuscules (normalisés avant analyse).
- La darija n'est pas couverte par le modèle NLP.
- L'ingestion recharge tout à chaque exécution ; en production, elle serait incrémentale.
