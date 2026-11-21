"""
DataGuard — ingestion : charge toutes les sources, TELLES QUELLES, dans le schéma `raw`.

Principe ELT : on ne nettoie rien ici. Toutes les colonnes sont stockées en TEXT
(aucune ligne rejetée à cause d'un format inattendu), avec deux colonnes techniques :
  _source_file : d'où vient la ligne (traçabilité)
  _loaded_at   : quand elle a été chargée
Le nettoyage est fait ensuite par dbt (couche staging), où il est testé et documenté.

Sources :
  base CRM (PostgreSQL)       crm.clients, crm.contrats   → raw.crm_clients, raw.crm_contrats
  exports facturation (CSV)   data/landing/billing         → raw.factures
  CDR réseau (CSV)            data/landing/network         → raw.cdr
  centre d'appel (JSON)       data/landing/callcenter      → raw.tickets
  antennes (OpenCelliD, CSV)  data/external/opencellid     → raw.antennes

Chargement complet à chaque exécution (simple et rejouable). En production,
on passerait à un chargement incrémental (seulement les nouveaux fichiers).

Lancer :  .venv\\Scripts\\python.exe -m ingestion.load_raw
"""
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from psycopg import sql

from scanner.db import connect

ROOT = Path(__file__).resolve().parent.parent
LANDING = ROOT / "data/landing"
CELLS_DIR = ROOT / "data/external/opencellid"
CELL_COLUMNS = ["radio", "mcc", "net", "area", "cell", "unit", "lon", "lat", "range",
                "samples", "changeable", "created", "updated", "averageSignal"]


def read_text(path: Path) -> tuple[str, str]:
    """Lit un fichier en essayant UTF-8, puis l'ancien encodage Windows (cp1252)."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 (caractères remplacés)"


def create_table(cur, table: str, columns: list[str]):
    cols = [sql.SQL("{} TEXT").format(sql.Identifier(c)) for c in columns]
    cols += [sql.SQL("_source_file TEXT"), sql.SQL("_loaded_at TIMESTAMPTZ")]
    cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier("raw", table)))
    cur.execute(sql.SQL("CREATE TABLE {} ({})").format(sql.Identifier("raw", table), sql.SQL(", ").join(cols)))


def copy_rows(cur, table: str, columns: list[str], rows, source: str, loaded_at) -> int:
    target = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier("raw", table),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns + ["_source_file", "_loaded_at"]))
    n = 0
    with cur.copy(target) as cp:
        for r in rows:
            cp.write_row([None if v is None else str(v) for v in r] + [source, loaded_at])
            n += 1
    return n


def load_csv_folder(cur, folder: Path, pattern: str, table: str, delimiter: str, log, loaded_at,
                    header: list[str] | None = None):
    files = sorted(p for p in folder.rglob(pattern) if p.is_file())
    columns = None
    for path in files:
        text, encoding = read_text(path)
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        file_columns = header or next(reader)
        if columns is None:
            columns = file_columns
            create_table(cur, table, columns)
        elif file_columns != columns:
            raise ValueError(f"{path.name} : colonnes différentes des fichiers précédents")
        n = copy_rows(cur, table, columns, reader, path.name, loaded_at)
        log.append((table, path.name, n, encoding))


def load_tickets(cur, log, loaded_at):
    """Le JSON est imbriqué : on l'aplatit (client.id → client_id, etc.)."""
    columns = ["ticket_id", "ouvert_le", "canal", "client_id", "client_tel", "motif", "notes", "agent_matricule"]
    create_table(cur, "tickets", columns)
    for path in sorted((LANDING / "callcenter").glob("*.json")):
        text, encoding = read_text(path)
        rows = ([t.get("ticket_id"), t.get("ouvert_le"), t.get("canal"),
                 (t.get("client") or {}).get("id"), (t.get("client") or {}).get("tel"),
                 t.get("motif"), t.get("notes"), (t.get("agent") or {}).get("matricule")]
                for t in json.loads(text))
        log.append(("tickets", path.name, copy_rows(cur, "tickets", columns, rows, path.name, loaded_at), encoding))


def replicate_crm(cur, log, loaded_at):
    """Réplication base → raw (ce que ferait un outil comme Airbyte ou Fivetran)."""
    for src, dst in [("clients", "crm_clients"), ("contrats", "crm_contrats")]:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier("raw", dst)))
        cur.execute(sql.SQL("CREATE TABLE {dst} AS SELECT *, %s::text AS _source_file, "
                            "%s::timestamptz AS _loaded_at FROM {src}").format(
            dst=sql.Identifier("raw", dst), src=sql.Identifier("crm", src)), (f"crm.{src}", loaded_at))
        log.append((dst, f"crm.{src}", cur.rowcount, "base de données"))


def main():
    loaded_at = datetime.now(timezone.utc)
    log = []
    with connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        replicate_crm(cur, log, loaded_at)
        load_csv_folder(cur, LANDING / "billing", "*.csv", "factures", ";", log, loaded_at)
        load_csv_folder(cur, LANDING / "network", "*.csv", "cdr", ",", log, loaded_at)
        load_tickets(cur, log, loaded_at)
        load_csv_folder(cur, CELLS_DIR, "*.csv", "antennes", ",", log, loaded_at, header=CELL_COLUMNS)

        cur.execute("""CREATE TABLE IF NOT EXISTS raw._ingestion_log (
                           table_name TEXT, source TEXT, n_rows INT, encoding TEXT, loaded_at TIMESTAMPTZ)""")
        cur.executemany("INSERT INTO raw._ingestion_log VALUES (%s, %s, %s, %s, %s)",
                        [(*entry, loaded_at) for entry in log])

    print(f"Ingestion du {loaded_at:%d/%m/%Y %H:%M} UTC")
    for table, source, n, encoding in log:
        print(f"  raw.{table:<13} ← {source:<26} {n:>6} lignes  ({encoding})")


if __name__ == "__main__":
    main()
