"""
DataGuard — anonymisation du texte libre (méthode ANONYMIZE_TEXT).

Le NER (Presidio/spaCy) ne peut pas tourner dans une vue SQL. On pré-calcule donc
en Python le texte anonymisé de chaque valeur, et on le range dans
`governance.text_anonymized`, indexé par l'empreinte md5 du texte original.
La vue dbt retrouve ensuite la version anonymisée grâce à cette empreinte.

  « Le client Abou Lamine, CIN U332181, signale des coupures à Fès. »
→ « Le client <PERSON>, CIN <CIN>, signale des coupures à Fès. »

On ne remplace pas les villes : seules, elles n'identifient personne et restent
utiles pour analyser les réclamations par zone.
"""
import hashlib

from psycopg import sql

from scanner.detection import analyzer
from scanner import rules

ENTITIES = ["PERSON"] + [f"MA_{t}" for t in rules.TEXT_PATTERNS]

# À incrémenter quand les règles changent : les textes déjà anonymisés avec une
# ancienne version sont alors recalculés (sinon le cache garderait d'anciennes fuites).
ANONYMIZER_VERSION = 3   # v3 : téléphones et IBAN dans leurs formats « sales »

TAGS = {"PERSON_AR": "PERSON"}   # un nom en arabe reste un <PERSON>


def anonymize_text(text: str) -> str:
    results = analyzer().analyze(text, language="fr", entities=ENTITIES)
    # Si deux détections se chevauchent, on garde la plus longue.
    results.sort(key=lambda r: (r.start, -(r.end - r.start)))
    kept, last_end = [], -1
    for r in results:
        if r.start >= last_end:
            kept.append(r)
            last_end = r.end
    # On remplace en partant de la fin, pour ne pas décaler les positions.
    for r in reversed(kept):
        tag = r.entity_type.removeprefix("MA_")
        text = text[:r.start] + f"<{TAGS.get(tag, tag)}>" + text[r.end:]
    return text


def run(conn) -> int:
    """Anonymise les colonnes dont la politique ANONYMIZE_TEXT est approuvée ou en attente.
    Renvoie le nb de textes traités."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS governance.text_anonymized (
            table_name TEXT, column_name TEXT, text_hash TEXT, anonymized TEXT,
            PRIMARY KEY (table_name, column_name, text_hash))""")
    conn.execute("ALTER TABLE governance.text_anonymized ADD COLUMN IF NOT EXISTS version INT DEFAULT 1")
    conn.execute("DELETE FROM governance.text_anonymized WHERE version < %s", (ANONYMIZER_VERSION,))
    targets = conn.execute("""
        SELECT table_name, column_name FROM governance.policy
        WHERE status IN ('approuvée', 'proposée')      -- protection par défaut, comme dans dbt
          AND masking_method = 'ANONYMIZE_TEXT'""").fetchall()

    total = 0
    for table_name, column_name in targets:
        done = {h for (h,) in conn.execute(
            "SELECT text_hash FROM governance.text_anonymized WHERE table_name = %s AND column_name = %s",
            (table_name, column_name))}
        texts = conn.execute(sql.SQL("SELECT DISTINCT {c} FROM {t} WHERE {c} IS NOT NULL").format(
            c=sql.Identifier(column_name), t=sql.Identifier(*table_name.split(".")))).fetchall()
        new_rows = []
        for (text,) in texts:
            h = hashlib.md5(text.encode("utf-8")).hexdigest()   # = md5() de PostgreSQL
            if h not in done:                                    # incrémental : on ne refait pas le travail
                new_rows.append((table_name, column_name, h, anonymize_text(text), ANONYMIZER_VERSION))
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO governance.text_anonymized
                               (table_name, column_name, text_hash, anonymized, version)
                               VALUES (%s, %s, %s, %s, %s)""", new_rows)
        total += len(new_rows)
    return total
