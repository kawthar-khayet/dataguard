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
    if events:
        print(f"\nCatalogue — {len(events)} événement(s) :")
        for table, column, kind, old, new in events:
            print(f"  [{kind}] {table}.{column} : {old or '∅'} → {new or '∅'}")
    else:
        print("Catalogue : aucun changement depuis le scan précédent.")
    if policy_changes:
        print(f"\nPolitiques — {len(policy_changes)} changement(s), en attente de validation :")
        for kind, table, column, detail in policy_changes:
            print(f"  [{kind}] {table}.{column} : {detail}")
    else:
        print("Politiques : aucun changement.")


if __name__ == "__main__":
    main()
