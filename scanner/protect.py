"""
DataGuard — application des politiques approuvées.

  1. anonymise le texte libre (Presidio)            → governance.text_anonymized
  2. dbt build --select tag:protected               → vues masquées analyst / support
                                                     + tests de non-fuite
  3. vérifie les droits : aucun rôle « analyst » ou « support_client »
     ne doit pouvoir lire les couches techniques (crm, raw, staging, marts)
  4. marque les politiques approuvées comme « appliquées »

Lancer :  .venv\\Scripts\\python.exe -W ignore -m scanner.protect
"""
import sys

from pipeline.dbt import run_dbt
from scanner import anonymize
from scanner.db import connect

TECHNICAL_SCHEMAS = ["crm", "raw", "staging", "marts"]
EXPOSED_ROLES = ["analyst", "support_client"]


def check_access(conn) -> list[str]:
    """Renvoie la liste des accès interdits trouvés (vide = tout va bien)."""
    leaks = []
    for role in EXPOSED_ROLES:
        for schema in TECHNICAL_SCHEMAS:
            if conn.execute("SELECT has_schema_privilege(%s, %s, 'USAGE')", (role, schema)).fetchone()[0]:
                leaks.append(f"{role} peut lire le schéma {schema}")
    return leaks


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with connect() as conn:
        n = anonymize.run(conn)
    print(f"1. Texte libre : {n} nouveau(x) texte(s) anonymisé(s)\n")

    print("2. dbt build --select tag:protected (vues masquées + tests de non-fuite)")
    result = run_dbt(["build", "--select", "tag:protected"])

    with connect() as conn:
        leaks = check_access(conn)
        print("\n3. Contrôle d'accès : " + ("✅ aucun accès analyste aux couches techniques"
                                         if not leaks else "❌ " + " ; ".join(leaks)))

        conn.execute("ALTER TABLE governance.policy ADD COLUMN IF NOT EXISTS applied_at TIMESTAMPTZ")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS governance.protection_run (
                run_at  TIMESTAMPTZ DEFAULT now(),
                success BOOLEAN,
                n_policies_applied INT)""")
        # Les vues ont-elles toutes été construites ? (indépendamment des tests de fuite)
        nodes = result.result.results if result.result else []
        views_ok = bool(nodes) and all(
            str(r.status) == "success" for r in nodes if r.node.resource_type == "model")
        # une politique qui n'est plus approuvée n'est plus appliquée
        conn.execute("UPDATE governance.policy SET applied_at = NULL WHERE status <> 'approuvée'")
        applied = 0
        if views_ok and not leaks:
            applied = conn.execute("""
                UPDATE governance.policy SET applied_at = coalesce(applied_at, now())
                WHERE status = 'approuvée'""").rowcount
        success = result.success and not leaks
        conn.execute("INSERT INTO governance.protection_run (success, n_policies_applied) VALUES (%s, %s)",
                     (success, applied))

    if success:
        with connect() as conn:
            pending = conn.execute(
                "SELECT count(*) FROM governance.policy WHERE status = 'proposée'").fetchone()[0]
        print(f"\n4. ✅ Protection appliquée : {applied} politique(s) approuvée(s)"
              + (f", {pending} en attente de validation (protégées par défaut)" if pending else ""))
        return 0
    print(f"\n4. ❌ Échec : {applied} politique(s) appliquée(s), mais des données personnelles "
          "restent exposées (voir ci-dessus).")
    print("   Approuve les politiques en attente dans l'interface, puis relance.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
