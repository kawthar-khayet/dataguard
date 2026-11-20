"""
DataGuard — étape 3 : le catalogue de données.

Trois tables dans le schéma `governance` :
  - detection        : TOUS les résultats de TOUS les scans (on ne supprime jamais rien)
  - catalog          : l'état ACTUEL de chaque colonne (une ligne par colonne)
  - catalog_history  : le journal des CHANGEMENTS entre deux scans
                       (nouvelle colonne, type qui change, colonne disparue…)

Pourquoi un historique ? Pour la traçabilité (prouver à un audit CNDP ce qu'on savait
et quand), et pour détecter les dérives : si une colonne « non sensible » se met
à contenir des téléphones, c'est un événement à signaler.

Le catalogue ne contient aucune valeur des données sources : seulement des
types, des scores et des explications.
"""
from scanner.detection import Detection

DDL = """
CREATE TABLE IF NOT EXISTS governance.detection (
    run_id      INT REFERENCES governance.scan_run,
    table_name  TEXT,
    column_name TEXT,
    pii_type    TEXT,
    category    TEXT,
    sensitivity TEXT,
    confidence  REAL,
    decision    TEXT,
    evidence    TEXT,
    PRIMARY KEY (run_id, table_name, column_name)
);
CREATE TABLE IF NOT EXISTS governance.catalog (
    table_name  TEXT,
    column_name TEXT,
    pii_type    TEXT,
    category    TEXT,
    sensitivity TEXT,
    confidence  REAL,
    decision    TEXT,
    evidence    TEXT,
    first_seen_run INT,
    last_run_id    INT,
    is_active   BOOLEAN DEFAULT TRUE,      -- FALSE si la colonne a disparu de la source
    updated_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (table_name, column_name)
);
CREATE TABLE IF NOT EXISTS governance.catalog_history (
    event_id    SERIAL PRIMARY KEY,
    run_id      INT,
    table_name  TEXT,
    column_name TEXT,
    event_type  TEXT,   -- NOUVELLE_COLONNE, CHANGEMENT_TYPE, CHANGEMENT_DECISION, COLONNE_DISPARUE
    old_value   TEXT,
    new_value   TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);
"""


def _label(pii_type, decision) -> str:
    return f"{decision} ({pii_type})" if pii_type else decision


def update_catalog(conn, run_id: int, detections: list[Detection]) -> list[tuple]:
    """Enregistre un scan, met à jour le catalogue, et renvoie les événements créés."""
    conn.execute(DDL)

    # 1. Historique complet : on garde le résultat brut de ce scan
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO governance.detection VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [(run_id, d.table_name, d.column_name, d.pii_type, d.category, d.sensitivity,
              d.confidence, d.decision, d.evidence) for d in detections])

    # 2. Comparaison avec l'état actuel du catalogue
    current = {(t, c): (typ, dec) for t, c, typ, dec in conn.execute(
        "SELECT table_name, column_name, pii_type, decision FROM governance.catalog WHERE is_active")}
    events = []
    for d in detections:
        key = (d.table_name, d.column_name)
        if key not in current:
            events.append((*key, "NOUVELLE_COLONNE", None, _label(d.pii_type, d.decision)))
            continue
        old_type, old_decision = current[key]
        if old_type != d.pii_type:
            events.append((*key, "CHANGEMENT_TYPE", old_type, d.pii_type))
        elif old_decision != d.decision:
            events.append((*key, "CHANGEMENT_DECISION", old_decision, d.decision))
    scanned = {(d.table_name, d.column_name) for d in detections}
    for key in current.keys() - scanned:
        events.append((*key, "COLONNE_DISPARUE", _label(*current[key]), None))

    # 3. Mise à jour du catalogue (insert ou update = "upsert")
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO governance.catalog
                (table_name, column_name, pii_type, category, sensitivity, confidence,
                 decision, evidence, first_seen_run, last_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (table_name, column_name) DO UPDATE SET
                pii_type = EXCLUDED.pii_type, category = EXCLUDED.category,
                sensitivity = EXCLUDED.sensitivity, confidence = EXCLUDED.confidence,
                decision = EXCLUDED.decision, evidence = EXCLUDED.evidence,
                last_run_id = EXCLUDED.last_run_id, is_active = TRUE, updated_at = now()
        """, [(d.table_name, d.column_name, d.pii_type, d.category, d.sensitivity,
               d.confidence, d.decision, d.evidence, run_id, run_id) for d in detections])
        for t, c in current.keys() - scanned:
            cur.execute("""UPDATE governance.catalog SET is_active = FALSE, updated_at = now()
                           WHERE table_name = %s AND column_name = %s""", (t, c))
        cur.executemany(
            """INSERT INTO governance.catalog_history
               (run_id, table_name, column_name, event_type, old_value, new_value)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            [(run_id, *e) for e in events])
    return events
