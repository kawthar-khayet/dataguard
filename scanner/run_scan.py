"""
DataGuard — scan complet : découverte → détection → catalogue.

Lancer :  .venv\\Scripts\\python.exe -W ignore -m scanner.run_scan
"""
from collections import Counter

from scanner import discovery
from scanner.catalog import update_catalog
from scanner.db import connect
from scanner.detection import detect_all
from scanner.policy import propose_policies


def main():
    run_id, profiles = discovery.run()
    detections = detect_all(profiles)
    with connect() as conn:
        events = update_catalog(conn, run_id, detections)
        policy_changes = propose_policies(conn, run_id)

    counts = Counter(d.decision for d in detections)
    print(f"Scan n°{run_id} : {len(detections)} colonnes analysées")
    print(f"  PII : {counts['PII']}   À vérifier : {counts['À vérifier']}   "
          f"Non sensibles : {counts['Non sensible']}")
    by_layer = Counter(d.table_name.split(".")[0] for d in detections if d.decision != "Non sensible")
    print("  Colonnes sensibles par couche : " + ", ".join(f"{k} {v}" for k, v in by_layer.items()))

    # Au premier scan, tout est « nouveau » : on résume au lieu de tout lister.
    if not events:
        print("Catalogue : aucun changement depuis le scan précédent.")
    elif all(e[2] == "NOUVELLE_COLONNE" for e in events) and len(events) > 20:
        print(f"\nCatalogue : {len(events)} colonnes enregistrées (premier scan).")
    else:
        print(f"\nCatalogue — {len(events)} événement(s) :")
        for table, column, kind, old, new in events:
            print(f"  [{kind}] {table}.{column} : {old or '∅'} → {new or '∅'}")

    if policy_changes:
        kinds = Counter(c[0] for c in policy_changes)
        print(f"\nPolitiques : {dict(kinds)} — en attente de validation dans l'interface.")
        for kind, table, column, detail in policy_changes:
            if not table.startswith(("crm.", "raw.", "staging.")):   # les marts, en détail
                print(f"  [{kind}] {table}.{column} : {detail}")
    else:
        print("Politiques : aucun changement.")


if __name__ == "__main__":
    main()
