"""
DataGuard — simulation des systèmes d'un opérateur télécom, avec leur désordre réel.

Base réelle :
  - data/external/telco/       → les 7 043 clients IBM Telco (services, contrats, factures, résiliations)
  - data/external/opencellid/  → les vraies antennes mobiles du Maroc (OpenCelliD, CC BY-SA 4.0)
Ajouté par simulation :
  - les données personnelles (noms, CIN, téléphones, IBAN…) : 100 % synthétiques
  - le désordre typique de systèmes qui ont grandi séparément

Sorties :
  PostgreSQL  crm.clients, crm.contrats      (base du CRM)
              crm.clients_backup_2019          (vieille copie oubliée : « shadow data »)
  Fichiers    data/landing/billing/*.csv       (exports de facturation, un par mois)
              data/landing/network/*.csv       (CDR : détail des appels)
              data/landing/callcenter/*.json   (tickets du centre d'appel)
  Vérité      governance.ground_truth_dups     (quels comptes CRM sont des doublons)

Lancer :  .venv\\Scripts\\python.exe generator\\sources.py
"""
import csv
import json
import math
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.db import connect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TELCO_CSV = ROOT / "data/external/telco/WA_Fn-UseC_-Telco-Customer-Churn.csv"
CELLS_DIR = ROOT / "data/external/opencellid"
LANDING = ROOT / "data/landing"

SEED = 42
TODAY = date(2026, 11, 20)
BILLING_MONTHS = [(2026, m) for m in range(6, 12)]   # juin → novembre 2026
DUPLICATE_RATE = 0.05     # 5 % des clients ont un 2e compte dans le CRM
CDR_CLIENTS = 1500        # clients dont on simule les appels de novembre
USD_TO_MAD = 10           # Telco est en dollars : on convertit en dirhams

rng = random.Random(SEED)
Faker.seed(SEED)
fk_latin, fk_arabe, fk = Faker("fr_DZ"), Faker("ar_DZ"), Faker("fr_FR")

# Coordonnées approximatives des villes : sert à choisir les antennes proches du client.
CITIES = {
    "Casablanca": (33.57, -7.59), "Rabat": (34.02, -6.84), "Marrakech": (31.63, -8.01),
    "Fès": (34.03, -5.00), "Tanger": (35.76, -5.83), "Agadir": (30.43, -9.60),
    "Oujda": (34.68, -1.91), "Meknès": (33.90, -5.55),
}
CITY_WEIGHTS = [30, 15, 12, 11, 10, 8, 7, 7]
# Façons dont les agents saisissent réellement les villes (dont accents cassés par un mauvais encodage)
CITY_VARIANTS = {
    "Casablanca": ["Casablanca", "CASABLANCA", "casa", "Casa ", "Dar El Beida"],
    "Rabat": ["Rabat", "RABAT", "rabat "],
    "Marrakech": ["Marrakech", "Marrakesh", "MARRAKECH"],
    "Fès": ["Fès", "Fes", "FES", "FÃ¨s"],
    "Tanger": ["Tanger", "Tangier", "TANGER"],
    "Agadir": ["Agadir", "agadir"],
    "Oujda": ["Oujda", "OUJDA"],
    "Meknès": ["Meknès", "Meknes", "MeknÃ¨s"],
}
PAYMENT = {"Bank transfer (automatic)": "Prélèvement bancaire", "Credit card (automatic)": "Carte bancaire",
           "Electronic check": "Paiement en ligne", "Mailed check": "Chèque"}
CONTRACT = {"Month-to-month": "Sans engagement", "One year": "1 an", "Two year": "2 ans"}
INTERNET = {"DSL": "ADSL", "Fiber optic": "Fibre", "No": "Aucun"}
OPTIONS = {"OnlineSecurity": "securite", "OnlineBackup": "sauvegarde", "DeviceProtection": "protection",
           "TechSupport": "assistance", "StreamingTV": "tv", "StreamingMovies": "films"}


# --- Valeurs « propres » (la vérité) ------------------------------------------------
def person(gender: str) -> str:
    f = fk_arabe if rng.random() < 0.15 else fk_latin
    first = f.first_name_female() if gender == "Female" else f.first_name_male()
    return f"{f.last_name()} {first}"

def new_phone() -> str:
    return "0" + rng.choice("67") + "".join(rng.choices("0123456789", k=8))

def new_cin() -> str:
    letters = "".join(rng.choices("ABCDEFGHJKLMNPRSTUVWXYZ", k=rng.choice([1, 2])))
    return letters + "".join(rng.choices("0123456789", k=rng.choice([5, 6])))

def new_iban() -> str:
    return "MA" + "".join(rng.choices("0123456789", k=26))


# --- Le désordre ------------------------------------------------------------------------
def messy_phone(p: str) -> str:
    d = p[1:]   # sans le 0
    return rng.choice([p, p, f"{p[:2]} {p[2:4]} {p[4:6]} {p[6:8]} {p[8:]}", ".".join([p[i:i+2] for i in range(0, 10, 2)]),
                       f"+212{d}", f"+212 {d[0]} {d[1:3]} {d[3:5]} {d[5:7]} {d[7:]}", f"212{d}"])

def messy_cin(c: str) -> str:
    letters = c.rstrip("0123456789")
    return rng.choice([c, c, c.lower(), f"{letters} {c[len(letters):]}", f" {c} "])

def messy_date(d: date) -> str:
    return rng.choice([d.isoformat(), d.strftime("%d/%m/%Y"), d.strftime("%d-%m-%y")])

def placeholder(value: str, rate: float) -> str:
    return rng.choice(["N/A", "", "inconnu", "-"]) if rng.random() < rate else value

def grouped_iban(i: str) -> str:   # MA64 0110 1234 ...
    return " ".join(i[k:k+4] for k in range(0, len(i), 4))


# --- 1. CRM ------------------------------------------------------------------------------
def build_crm(telco: pd.DataFrame):
    clients, contrats, truth = [], [], {}
    for r in telco.itertuples():
        city = rng.choices(list(CITIES), CITY_WEIGHTS)[0]
        tenure = int(r.tenure)
        created = TODAY - timedelta(days=30 * tenure + rng.randint(0, 25))
        c = {"id": r.customerID, "nom": person(r.gender), "cin": new_cin(), "tel": new_phone(),
             "email": fk.ascii_free_email(), "naiss": fk.date_of_birth(minimum_age=18, maximum_age=80),
             "adresse": fk.street_address(), "ville": city, "genre": r.gender, "creation": created,
             "iban": new_iban(), "churn": r.Churn == "Yes", "phone_service": r.PhoneService == "Yes",
             "paiement": PAYMENT[r.PaymentMethod], "mensualite": round(float(r.MonthlyCharges) * USD_TO_MAD, 2)}
        truth[c["id"]] = c
        clients.append((c["id"], c["nom"], messy_cin(c["cin"]), placeholder(messy_phone(c["tel"]), 0.02),
                        placeholder(c["email"], 0.04), placeholder(messy_date(c["naiss"]), 0.02),
                        c["adresse"], rng.choice(CITY_VARIANTS[city]),
                        rng.choice(["Female", "F", "Femme"]) if r.gender == "Female" else rng.choice(["Male", "M", "Homme"]),
                        created.isoformat()))
        resil = (TODAY - timedelta(days=rng.randint(0, 170))) if c["churn"] else None
        c["resiliation"] = resil
        options = ",".join(v for k, v in OPTIONS.items() if getattr(r, k) == "Yes")
        contrats.append((r.customerID, CONTRACT[r.Contract], INTERNET[r.InternetService],
                         "oui" if c["phone_service"] else "non", options, c["paiement"],
                         f"{c['mensualite']:.2f}",
                         r.TotalCharges,                       # VRAI désordre Telco : 11 valeurs vides
                         created.isoformat(), "résilié" if c["churn"] else "actif",
                         resil.isoformat() if resil else ""))

    # Doublons : la même personne recréée plus tard en agence, saisie différemment
    dups = []
    for c in rng.sample(list(truth.values()), int(len(truth) * DUPLICATE_RATE)):
        dup_id = f"{rng.randint(1000, 9999)}-{''.join(rng.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=5))}"
        nom = c["nom"]
        parts = nom.split(" ", 1)
        nom = rng.choice([nom.upper(), f"{parts[-1]} {parts[0]}", f"  {nom}"])
        clients.append((dup_id, nom, messy_cin(c["cin"]), messy_phone(c["tel"]),
                         placeholder(c["email"], 0.5), placeholder(messy_date(c["naiss"]), 0.3),
                         c["adresse"].upper(), rng.choice(CITY_VARIANTS[c["ville"]]),
                         c["genre"][0], (c["creation"] + timedelta(days=rng.randint(30, 400))).isoformat()))
        dups.append((dup_id, c["id"]))
    rng.shuffle(clients)
    return clients, contrats, truth, dups


# --- 2. Facturation (exports CSV mensuels) -------------------------------------------------
def write_billing(truth: dict):
    out = LANDING / "billing"
    out.mkdir(parents=True, exist_ok=True)
    seq = 0
    for year, month in BILLING_MONTHS:
        start = date(year, month, 1)
        rows = []
        for c in truth.values():
            if c["creation"] > start or (c["resiliation"] and c["resiliation"] < start):
                continue   # pas client ce mois-là
            seq += 1
            d = date(year, month, 5)
            # Changement de système en septembre : le format des dates change
            date_txt = d.isoformat() if month < 9 else d.strftime("%d/%m/%Y")
            montant = "N/A" if rng.random() < 0.01 else f"{c['mensualite']:.2f}".replace(".", ",") + " DH"
            iban = (grouped_iban(c["iban"]) if c["paiement"] == "Prélèvement bancaire"
                    else "**** **** **** " + c["iban"][-4:] if c["paiement"] == "Carte bancaire" else "")
            msisdn = "212" + c["tel"][1:] if rng.random() < 0.85 else messy_phone(c["tel"])
            rows.append([f"F{year}{month:02d}-{seq:07d}", msisdn, montant, date_txt, c["paiement"], iban])
        rows += rng.sample(rows, len(rows) // 200)          # ~0,5 % de lignes exportées deux fois
        encoding = "cp1252" if month == 7 else "utf-8"       # un export de juillet en ancien encodage Windows
        path = out / f"factures_{year}-{month:02d}.csv"
        with open(path, "w", newline="", encoding=encoding) as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["num_facture", "msisdn", "montant", "date_facture", "mode_paiement", "iban"])
            w.writerows(rows)
        print(f"  {path.relative_to(ROOT)}  {len(rows):>6} lignes  ({encoding})")


# --- 3. Réseau : CDR sur les vraies antennes -------------------------------------------------
def load_cells() -> pd.DataFrame:
    files = [p for p in CELLS_DIR.rglob("*") if p.is_file() and ".csv" in p.name]
    if not files:
        sys.exit(f"Aucun fichier OpenCelliD trouvé dans {CELLS_DIR}")
    cols = ["radio", "mcc", "net", "area", "cell", "unit", "lon", "lat", "range",
            "samples", "changeable", "created", "updated", "averageSignal"]
    df = pd.read_csv(files[0], header=None, names=cols)   # l'export n'a pas d'en-tête
    df["cell_id"] = df.mcc.astype(str) + "-" + df.net.astype(str) + "-" + df.area.astype(str) + "-" + df.cell.astype(str)
    return df

def cells_by_city(cells: pd.DataFrame) -> dict:
    near = {}
    for city, (lat, lon) in CITIES.items():
        dist = ((cells.lat - lat) ** 2 + ((cells.lon - lon) * math.cos(math.radians(lat))) ** 2) ** 0.5 * 111
        close = cells[dist < 25]
        near[city] = (close if len(close) >= 3 else cells.loc[dist.nsmallest(5).index]).cell_id.tolist()
    return near

def write_cdr(truth: dict, cells: pd.DataFrame):
    out = LANDING / "network"
    out.mkdir(parents=True, exist_ok=True)
    near = cells_by_city(cells)
    all_cells = cells.cell_id.tolist()
    callers = [c for c in truth.values() if c["phone_service"] and not c["churn"]]
    rows = []
    for c in rng.sample(callers, min(CDR_CLIENTS, len(callers))):
        for _ in range(rng.randint(15, 60)):
            ts = datetime(2026, 11, 1) + timedelta(seconds=rng.randint(0, 19 * 86400))
            cell = rng.choice(near[c["ville"]]) if rng.random() < 0.9 else rng.choice(all_cells)  # 10 % en déplacement
            duree = rng.choice(["", "-1"]) if rng.random() < 0.01 else str(int(rng.expovariate(1 / 120)) + 1)
            rows.append(["212" + c["tel"][1:], "212" + new_phone()[1:], ts.strftime("%Y-%m-%d %H:%M:%S"),
                         duree, cell, rng.choice(["voix", "voix", "sms"])])
    path = out / "cdr_2026-11.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["msisdn_appelant", "msisdn_appele", "date_heure", "duree_sec", "cell_id", "type"])
        w.writerows(rows)
    print(f"  {path.relative_to(ROOT)}  {len(rows):>6} lignes")


# --- 4. Centre d'appel : tickets JSON ---------------------------------------------------------
NOTES = [
    "Client {nom} (CIN {cin}) appelle pour des coupures fréquentes à {ville}. Rappeler au {tel}.",
    "Mme/M. {nom} conteste la facture de {mois}. Envoyer le détail à {email}.",
    "Demande de résiliation : le client part chez un concurrent, offre jugée trop chère.",
    "{nom} demande le remboursement d'un double prélèvement sur le compte {iban}.",
    "Débit internet très faible depuis une semaine, technicien à planifier.",
    "Le client demande la portabilité du numéro {tel} vers un autre opérateur.",
    "Réclamation réseau : pas de 4G dans le quartier, plusieurs voisins concernés.",
    "Client mécontent du service, menace de résilier. Contact : {tel} / {email}",
]
MOTIFS = ["Réseau", "Facturation", "Résiliation", "Portabilité", "Technique"]

def write_tickets(truth: dict):
    out = LANDING / "callcenter"
    out.mkdir(parents=True, exist_ok=True)
    people = list(truth.values())
    targets = [c for c in people if c["churn"]] + rng.sample(people, 600)
    tickets = []
    for i, c in enumerate(targets, 1):
        for _ in range(rng.randint(1, 3) if c["churn"] else 1):
            opened = datetime(2026, 9, 1) + timedelta(minutes=rng.randint(0, 80 * 24 * 60))
            note = rng.choice(NOTES).format(
                nom=c["nom"], cin=c["cin"], ville=c["ville"], tel=messy_phone(c["tel"]),
                email=c["email"], iban=grouped_iban(c["iban"]), mois=rng.choice(["septembre", "octobre"]))
            tickets.append({
                "ticket_id": f"T-{len(tickets) + 1:06d}",
                "ouvert_le": opened.isoformat(timespec="seconds"),
                "canal": rng.choice(["téléphone", "agence", "application", "chat"]),
                "client": {"id": None if rng.random() < 0.1 else c["id"], "tel": messy_phone(c["tel"])},
                "motif": "Résiliation" if c["churn"] and rng.random() < 0.5 else rng.choice(MOTIFS),
                "notes": note,
                "agent": {"matricule": f"AG{rng.randint(1, 80):03d}"},
            })
    for k in range(0, len(tickets), 1000):    # un fichier par lot de 1000 tickets
        path = out / f"tickets_{k // 1000 + 1:02d}.json"
        path.write_text(json.dumps(tickets[k:k + 1000], ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {path.relative_to(ROOT)}  {len(tickets[k:k + 1000]):>6} tickets")


# --- Écriture du CRM dans PostgreSQL --------------------------------------------------------------
DDL = """
DROP SCHEMA IF EXISTS crm CASCADE;
CREATE SCHEMA crm;
-- Base « legacy » : presque tout est en texte libre, comme dans beaucoup de vieux CRM
CREATE TABLE crm.clients (
    id_client TEXT PRIMARY KEY, nom_complet TEXT, cin TEXT, tel TEXT, email TEXT,
    date_naiss TEXT, adresse TEXT, ville TEXT, genre TEXT, date_creation TEXT);
CREATE TABLE crm.contrats (
    id_client TEXT REFERENCES crm.clients, type_contrat TEXT, internet TEXT, telephonie TEXT,
    options TEXT, mode_paiement TEXT, mensualite TEXT, total_facture TEXT,
    date_debut TEXT, statut TEXT, date_resiliation TEXT);
-- Copie faite en 2019 avant une migration, jamais supprimée
CREATE TABLE crm.clients_backup_2019 (
    "CLIENT" TEXT, "CIN" TEXT, "GSM" TEXT, "MAIL" TEXT, "ADR" TEXT, "VILLE" TEXT);
CREATE TABLE IF NOT EXISTS governance.ground_truth_dups (dup_id TEXT PRIMARY KEY, master_id TEXT);
TRUNCATE governance.ground_truth_dups;
"""

def write_crm(clients, contrats, truth, dups):
    backup = [(c["nom"].upper(), c["cin"], c["tel"], c["email"], c["adresse"], c["ville"])
              for c in rng.sample(list(truth.values()), 2000)]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(DDL)
        for table, rows in [("crm.clients", clients), ("crm.contrats", contrats),
                            ("crm.clients_backup_2019", backup), ("governance.ground_truth_dups", dups)]:
            with cur.copy(f"COPY {table} FROM STDIN") as cp:
                for r in rows:
                    cp.write_row(r)
            print(f"  {table:<30} {len(rows):>6} lignes")


def main():
    telco = pd.read_csv(TELCO_CSV, dtype=str, keep_default_na=False)
    print(f"Telco : {len(telco)} clients réels chargés")
    clients, contrats, truth, dups = build_crm(telco)
    print("CRM (PostgreSQL) :")
    write_crm(clients, contrats, truth, dups)
    print("Facturation :")
    write_billing(truth)
    cells = load_cells()
    print(f"Réseau ({len(cells)} antennes OpenCelliD) :")
    write_cdr(truth, cells)
    print("Centre d'appel :")
    write_tickets(truth)


if __name__ == "__main__":
    main()
