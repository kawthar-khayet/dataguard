"""
DataGuard — étape 4 : le Policy Engine.

À partir du catalogue, il PROPOSE une politique pour chaque colonne sensible :
  - une méthode de masquage adaptée au type (hash, masquage partiel, généralisation…)
  - les rôles autorisés à voir la donnée en clair

Il n'applique RIEN lui-même : chaque politique naît au statut « proposée » et
attend la décision d'un administrateur (approuver / rejeter). Seules les politiques
« approuvées » seront appliquées par dbt à l'étape suivante.

Cycle de vie d'une politique :
    proposée ──► approuvée
             └─► rejetée        (ex. code_offre : l'administrateur confirme que ce n'est pas une PII)
    n'importe quel statut ──► obsolète   (la colonne a disparu ou son type a changé)
"""
from scanner import rules

DDL = """
CREATE TABLE IF NOT EXISTS governance.policy (
    policy_id      SERIAL PRIMARY KEY,
    table_name     TEXT,
    column_name    TEXT,
    pii_type       TEXT,
    sensitivity    TEXT,
    masking_method TEXT,
    clear_roles    TEXT[],     -- rôles qui voient la donnée en clair
    rationale      TEXT,       -- pourquoi cette politique (affiché à l'administrateur)
    status         TEXT DEFAULT 'proposée',
    proposed_run   INT,
    proposed_at    TIMESTAMPTZ DEFAULT now(),
    decided_by     TEXT,
    decided_at     TIMESTAMPTZ,
    comment        TEXT
);
-- au plus UNE politique « vivante » (non obsolète) par colonne
CREATE UNIQUE INDEX IF NOT EXISTS policy_one_live_per_column
    ON governance.policy (table_name, column_name) WHERE status <> 'obsolète';
"""


def propose_policies(conn, run_id: int) -> list[tuple]:
    """Compare le catalogue aux politiques existantes ; crée ou rend obsolète. Renvoie les changements."""
    conn.execute(DDL)
    sensitive = {(t, c): (typ, sens, dec) for t, c, typ, sens, dec in conn.execute("""
        SELECT table_name, column_name, pii_type, sensitivity, decision
        FROM governance.catalog
        WHERE is_active AND decision IN ('PII', 'À vérifier')""")}
    live = {(t, c): (pid, typ) for pid, t, c, typ in conn.execute("""
        SELECT policy_id, table_name, column_name, pii_type
        FROM governance.policy WHERE status <> 'obsolète'""")}

    changes = []
    # 1. Politiques devenues inutiles : colonne disparue, devenue non sensible, ou type changé
    for key, (pid, old_type) in live.items():
        if key not in sensitive or sensitive[key][0] != old_type:
            conn.execute("""UPDATE governance.policy SET status = 'obsolète', decided_at = now(),
                            comment = 'remplacée suite à un nouveau scan' WHERE policy_id = %s""", (pid,))
            changes.append(("OBSOLÈTE", *key, old_type))

    # 2. Nouvelles propositions pour les colonnes sensibles sans politique vivante
    #    (une politique déjà approuvée ou rejetée pour le même type est conservée telle quelle)
    still_live = {k for k, (pid, typ) in live.items() if k in sensitive and sensitive[k][0] == typ}
    for key, (pii_type, sensitivity, decision) in sensitive.items():
        if key in still_live:
            continue
        method, explanation = rules.MASKING[pii_type]
        clear_roles = rules.CLEAR_ACCESS.get(sensitivity, ["dpo"])
        rationale = f"{pii_type} ({sensitivity}) → {method} : {explanation}"
        if decision == "À vérifier":
            rationale += " | Détection incertaine : par prudence, on propose de masquer."
        conn.execute("""
            INSERT INTO governance.policy (table_name, column_name, pii_type, sensitivity,
                masking_method, clear_roles, rationale, proposed_run)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (*key, pii_type, sensitivity, method, clear_roles, rationale, run_id))
        changes.append(("PROPOSÉE", *key, f"{pii_type} → {method}"))
    return changes


def decide(conn, policy_id: int, approve: bool, decided_by: str, comment: str = "") -> None:
    """Décision humaine : appelée par l'interface de validation."""
    updated = conn.execute("""
        UPDATE governance.policy
        SET status = %s, decided_by = %s, decided_at = now(), comment = %s
        WHERE policy_id = %s AND status = 'proposée'""",
        ("approuvée" if approve else "rejetée", decided_by, comment, policy_id)).rowcount
    if updated == 0:
        raise ValueError(f"Politique {policy_id} introuvable ou déjà décidée")
