"""
DataGuard — générateur de données télécom synthétiques.

Remplit le schéma `source` de PostgreSQL avec de FAUSSES données (aucune personne réelle),
et écrit dans `governance.ground_truth` la liste des colonnes réellement sensibles :
elle servira plus tard à mesurer la précision du scanner.

Lancer :  .venv\\Scripts\\python.exe generator\\generate.py
Le script est relançable : il recrée les tables à chaque exécution.
"""
import os
import random
from datetime import date

import psycopg
from dotenv import load_dotenv
from faker import Faker

# --- Paramètres -------------------------------------------------------------
SEED = 42                 # même graine = mêmes données à chaque exécution
N_CLIENTS = 1000
N_RECLAMATIONS = 600
PART_NOMS_ARABES = 0.15   # 15 % des noms en alphabet arabe

random.seed(SEED)
Faker.seed(SEED)
fake_latin = Faker("fr_DZ")   # noms maghrébins en alphabet latin
fake_arabe = Faker("ar_DZ")   # noms maghrébins en alphabet arabe
fake = Faker("fr_FR")         # e-mails, rues, dates

VILLES = ["Casablanca", "Rabat", "Marrakech", "Fès", "Tanger", "Agadir", "Oujda", "Meknès"]
OFFRES = [("Forfait 5G 50Go", 99), ("Forfait 4G 20Go", 49), ("Fibre 100Mb", 349),
          ("Fibre 1Gb", 549), ("Prépayé Jawal", 0)]


# --- Formats marocains : une ligne Faker chacun -----------------------------
def nom():
    f = fake_arabe if random.random() < PART_NOMS_ARABES else fake_latin
    return f.name()

def cin():        # 1 ou 2 lettres + 5 ou 6 chiffres, ex. "AB123456", "J41234"
    return fake.bothify(random.choice(["?######", "??######", "??#####"]),
                        letters="ABCDEFGHIJKLMNPRSTUVWXYZ")

def telephone():  # formats mélangés, comme dans une vraie base
    return fake.numerify(random.choice(["06########", "07########",
                                        "+2126########", "06 ## ## ## ##"]))

def iban():       # MA + 26 chiffres (clé de contrôle non calculée)
    return fake.numerify("MA" + "#" * 26)

def code_offre(): # PIÈGE : ressemble à un CIN mais n'est PAS une donnée personnelle
    return fake.bothify("??#####", letters="FXPRT")


# --- Génération ---------------------------------------------------------------
def generer_clients():
    rows = []
    for i in range(1, N_CLIENTS + 1):
        rows.append((
            i, nom(), cin(), telephone(), fake.ascii_free_email(),
            fake.date_of_birth(minimum_age=18, maximum_age=80),
            fake.street_address(), random.choice(VILLES),
            fake.date_between(date(2018, 1, 1), date(2026, 10, 31)),
            random.choice(["Grand public", "Entreprise", "Jeune"]),
        ))
    return rows

def generer_abonnements(clients):
    rows, ab_id = [], 1
    for c in clients:
        for _ in range(random.choice([1, 1, 1, 2])):
            libelle, prix = random.choice(OFFRES)
            rows.append((
                ab_id, c[0],
                c[2],           # PIÈGE ref_client : contient le CIN, mais mal nommé
                code_offre(), libelle,
                telephone(),    # PIÈGE info2 : contient un téléphone, mais mal nommé
                fake.date_between(c[8], date(2026, 11, 1)),
                random.choice(["actif", "actif", "actif", "suspendu", "résilié"]),
                prix,
            ))
            ab_id += 1
    return rows

def generer_paiements(abonnements):
    rows, p_id = [], 1
    for a in abonnements:
        if a[8] == 0:   # prépayé : pas de prélèvement
            continue
        compte = iban()
        for _ in range(random.randint(1, 6)):
            rows.append((p_id, a[0], compte, a[8],
                         fake.date_between(a[6], date(2026, 11, 15)),
                         random.choice(["prélèvement", "carte", "agence"])))
            p_id += 1
    return rows

MODELES_RECLAMATION = [
    "Le client {nom}, CIN {cin}, signale des coupures réseau à {ville}. Rappeler au {tel}.",
    "Appel de {nom} : facture contestée, merci de le recontacter sur {email}.",
    "Débit fibre très faible depuis 3 jours à {ville}, client mécontent.",
    "{nom} demande la portabilité de son numéro {tel} vers un autre opérateur.",
    "Remboursement demandé sur le compte {iban} suite à un double prélèvement.",
    "Pas de réseau 4G dans le quartier, plusieurs clients concernés.",
]

def generer_reclamations(clients):
    rows = []
    for i in range(1, N_RECLAMATIONS + 1):
        c = random.choice(clients)
        texte = random.choice(MODELES_RECLAMATION).format(
            nom=c[1], cin=c[2], tel=c[3], email=c[4], ville=c[7], iban=iban())
        rows.append((i, c[0], fake.date_between(date(2025, 1, 1), date(2026, 11, 15)),
                     random.choice(["téléphone", "agence", "application", "e-mail"]), texte))
    return rows


# --- Vérité terrain : ce que le scanner DEVRAIT trouver -----------------------
# (table, colonne, est_pii, type_pii, sensibilité attendue)
GROUND_TRUTH = [
    ("clients", "client_id",        False, None,            "Interne"),
    ("clients", "nom_complet",      True,  "PERSON",        "Confidentiel"),
    ("clients", "cin",              True,  "CIN",           "Restreint"),
    ("clients", "telephone",        True,  "PHONE",         "Confidentiel"),
    ("clients", "email",            True,  "EMAIL",         "Confidentiel"),
    ("clients", "date_naissance",   True,  "DATE_OF_BIRTH", "Confidentiel"),
    ("clients", "adresse",          True,  "ADDRESS",       "Confidentiel"),
    ("clients", "ville",            False, None,            "Interne"),
    ("clients", "date_inscription", False, None,            "Interne"),
    ("clients", "segment",          False, None,            "Public"),
    ("abonnements", "abonnement_id",  False, None,    "Interne"),
    ("abonnements", "client_id",      False, None,    "Interne"),
    ("abonnements", "ref_client",     True,  "CIN",   "Restreint"),     # piège
    ("abonnements", "code_offre",     False, None,    "Public"),        # piège (faux positif)
    ("abonnements", "libelle_offre",  False, None,    "Public"),
    ("abonnements", "info2",          True,  "PHONE", "Confidentiel"),  # piège
    ("abonnements", "date_debut",     False, None,    "Interne"),
    ("abonnements", "statut",         False, None,    "Interne"),
    ("abonnements", "montant_mensuel",False, None,    "Interne"),
    ("paiements", "paiement_id",   False, None,   "Interne"),
    ("paiements", "abonnement_id", False, None,   "Interne"),
    ("paiements", "iban",          True,  "IBAN", "Restreint"),
    ("paiements", "montant",       False, None,   "Interne"),
    ("paiements", "date_paiement", False, None,   "Interne"),
    ("paiements", "mode_paiement", False, None,   "Public"),
    ("reclamations", "reclamation_id", False, None,        "Interne"),
    ("reclamations", "client_id",      False, None,        "Interne"),
    ("reclamations", "date_creation",  False, None,        "Interne"),
    ("reclamations", "canal",          False, None,        "Public"),
    ("reclamations", "commentaire",    True,  "FREE_TEXT", "Confidentiel"),  # NLP
]


# --- Écriture dans PostgreSQL -----------------------------------------------
DDL = """
DROP TABLE IF EXISTS source.reclamations, source.paiements, source.abonnements, source.clients;
DROP TABLE IF EXISTS governance.ground_truth;

CREATE TABLE source.clients (
    client_id        INT PRIMARY KEY,
    nom_complet      TEXT,
    cin              TEXT,
    telephone        TEXT,
    email            TEXT,
    date_naissance   DATE,
    adresse          TEXT,
    ville            TEXT,
    date_inscription DATE,
    segment          TEXT
);
CREATE TABLE source.abonnements (
    abonnement_id   INT PRIMARY KEY,
    client_id       INT REFERENCES source.clients,
    ref_client      TEXT,
    code_offre      TEXT,
    libelle_offre   TEXT,
    info2           TEXT,
    date_debut      DATE,
    statut          TEXT,
    montant_mensuel NUMERIC(8,2)
);
CREATE TABLE source.paiements (
    paiement_id   INT PRIMARY KEY,
    abonnement_id INT REFERENCES source.abonnements,
    iban          TEXT,
    montant       NUMERIC(8,2),
    date_paiement DATE,
    mode_paiement TEXT
);
CREATE TABLE source.reclamations (
    reclamation_id INT PRIMARY KEY,
    client_id      INT REFERENCES source.clients,
    date_creation  DATE,
    canal          TEXT,
    commentaire    TEXT
);
CREATE TABLE governance.ground_truth (
    table_name  TEXT,
    column_name TEXT,
    is_pii      BOOLEAN,
    pii_type    TEXT,
    sensitivity TEXT,
    PRIMARY KEY (table_name, column_name)
);
"""

def copier(cur, table, colonnes, rows):
    """COPY = la façon la plus rapide d'insérer beaucoup de lignes dans PostgreSQL."""
    with cur.copy(f"COPY {table} ({', '.join(colonnes)}) FROM STDIN") as cp:
        for r in rows:
            cp.write_row(r)
    print(f"  {table:<26} {len(rows):>6} lignes")


def main():
    load_dotenv()
    conninfo = (f"host=localhost port={os.environ['POSTGRES_PORT']} "
                f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
                f"password={os.environ['POSTGRES_PASSWORD']}")

    clients = generer_clients()
    abonnements = generer_abonnements(clients)
    paiements = generer_paiements(abonnements)
    reclamations = generer_reclamations(clients)

    with psycopg.connect(conninfo) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        print("Chargement :")
        copier(cur, "source.clients", ["client_id", "nom_complet", "cin", "telephone", "email",
               "date_naissance", "adresse", "ville", "date_inscription", "segment"], clients)
        copier(cur, "source.abonnements", ["abonnement_id", "client_id", "ref_client", "code_offre",
               "libelle_offre", "info2", "date_debut", "statut", "montant_mensuel"], abonnements)
        copier(cur, "source.paiements", ["paiement_id", "abonnement_id", "iban", "montant",
               "date_paiement", "mode_paiement"], paiements)
        copier(cur, "source.reclamations", ["reclamation_id", "client_id", "date_creation",
               "canal", "commentaire"], reclamations)
        copier(cur, "governance.ground_truth", ["table_name", "column_name", "is_pii",
               "pii_type", "sensitivity"], GROUND_TRUTH)
    print("Terminé.")


if __name__ == "__main__":
    main()
