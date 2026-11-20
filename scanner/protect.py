"""
DataGuard — application des politiques approuvées.

  1. anonymise le texte libre (Presidio)        → governance.text_anonymized
  2. lance `dbt build` : crée les vues protégées → schémas analyst et support
                         + exécute les tests de non-fuite
  3. si tout réussit, marque les politiques approuvées comme « appliquées »

Lancer :  .venv\\Scripts\\python.exe -W ignore -m scanner.protect
"""
import sys
from pathlib import Path

from dbt.cli.main import dbtRunner
from dotenv import load_dotenv

from scanner import anonymize
from scanner.db import connect

DBT_DIR = str(Path(__file__).resolve().parent.parent / "dbt")


def main() -> int:
    load_dotenv()   # dbt lit le mot de passe et le sel dans les variables d'environnement

    with connect() as conn:
        n = anonymize.run(conn)
    print(f"1. Texte libre : {n} nouveau(x) texte(s) anonymisé(s)\n")

    print("2. dbt build (vues protégées + tests de non-fuite)")
    result = dbtRunner().invoke(["build", "--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR])

    with connect() as conn:
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
        if views_ok:
            applied = conn.execute("""
                UPDATE governance.policy SET applied_at = coalesce(applied_at, now())
                WHERE status = 'approuvée'""").rowcount
        conn.execute("INSERT INTO governance.protection_run (success, n_policies_applied) VALUES (%s, %s)",
                     (result.success, applied))

    if result.success:
        print(f"\n3. ✅ Protection appliquée : {applied} politique(s) en vigueur")
        return 0
    print(f"\n3. ❌ Échec : {applied} politique(s) appliquée(s), mais des données personnelles "
          "apparaissent encore en clair (voir les tests ci-dessus).")
    print("   Approuve les politiques en attente dans l'interface, puis relance.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
