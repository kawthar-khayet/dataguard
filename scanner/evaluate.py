"""
DataGuard — lance découverte + détection, puis compare avec la vérité terrain.

Précision = parmi les colonnes que le scanner déclare PII, combien le sont vraiment ?
Rappel    = parmi les colonnes vraiment PII, combien le scanner en a trouvé ?
En protection des données, le RAPPEL est le plus important : une PII oubliée = une fuite.

Lancer :  .venv\\Scripts\\python.exe -m scanner.evaluate
"""
from scanner import discovery
from scanner.db import connect
from scanner.detection import detect_all


def main():
    run_id, profiles = discovery.run()
    detections = detect_all(profiles)

    with connect() as conn:
        truth = {(t, c): (pii, typ) for t, c, pii, typ in conn.execute(
            "SELECT table_name, column_name, is_pii, pii_type FROM governance.ground_truth")}

    tp = fp = fn = tn = review = 0
    print(f"Scan n°{run_id}\n")
    print(f"{'colonne':<28}{'décision':<14}{'type':<15}{'score':>6}  {'attendu':<14} explication")
    for d in detections:
        is_pii, expected = truth[(d.table_name, d.column_name)]
        flag = d.decision == "PII"
        if d.decision == "À vérifier":
            review += 1
            mark = "?"
        elif flag and is_pii:
            tp += 1; mark = "✓" if d.pii_type == expected or expected == "FREE_TEXT" else "~"
        elif flag and not is_pii:
            fp += 1; mark = "✗ FP"
        elif not flag and is_pii:
            fn += 1; mark = "✗ FN"
        else:
            tn += 1; mark = "✓"
        print(f"{d.table_name + '.' + d.column_name:<28}{d.decision:<14}{d.pii_type or '-':<15}"
              f"{d.confidence:>6}  {(expected or '-'):<14} {mark:<5} {d.evidence}")

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    print(f"\nPII trouvées : {tp}  |  faux positifs : {fp}  |  PII manquées : {fn}  |  "
          f"à vérifier : {review}  |  non sensibles correctes : {tn}")
    print(f"Précision : {precision:.0%}   Rappel : {recall:.0%}   "
          f"(les colonnes « à vérifier » partent en validation humaine)")


if __name__ == "__main__":
    main()
