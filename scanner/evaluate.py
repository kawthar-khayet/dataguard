"""
DataGuard — lance découverte + détection, puis compare avec la vérité terrain.

La vérité terrain (generator/ground_truth.csv) liste les colonnes RÉELLEMENT personnelles ;
toutes les autres colonnes sont considérées comme non sensibles.

Précision = parmi les colonnes que le scanner déclare PII, combien le sont vraiment ?
Rappel    = parmi les colonnes vraiment PII, combien le scanner en a trouvé ?
En protection des données, le RAPPEL est le plus important : une PII oubliée = une fuite.

Lancer :  .venv\\Scripts\\python.exe -W ignore -m scanner.evaluate
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

from scanner import discovery
from scanner.detection import detect_all

TRUTH = Path(__file__).resolve().parent.parent / "generator" / "ground_truth.csv"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with open(TRUTH, encoding="utf-8") as f:
        truth = {(r["table_name"], r["column_name"]): r["pii_type"] for r in csv.DictReader(f)}

    run_id, profiles = discovery.run()
    detections = detect_all(profiles)

    stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "review": 0})
    problems = []
    for d in detections:
        layer = d.table_name.split(".")[0]
        expected = truth.get((d.table_name, d.column_name))
        s = stats[layer]
        if d.decision == "À vérifier":
            s["review"] += 1
            problems.append(("?  à vérifier", d, expected))
        elif d.decision == "PII" and expected:
            s["tp"] += 1
            if d.pii_type != expected:
                problems.append(("~  mauvais type", d, expected))
        elif d.decision == "PII":
            s["fp"] += 1
            problems.append(("✗  faux positif", d, expected))
        elif expected:
            s["fn"] += 1
            problems.append(("✗  PII manquée", d, expected))

    print(f"Scan n°{run_id} : {len(detections)} colonnes dans {', '.join(discovery.SCHEMAS)}\n")
    print(f"{'couche':<10}{'PII trouvées':>13}{'faux positifs':>15}{'manquées':>10}{'à vérifier':>12}"
          f"{'précision':>11}{'rappel':>8}")
    total = {"tp": 0, "fp": 0, "fn": 0, "review": 0}
    for layer in discovery.SCHEMAS:
        s = stats[layer]
        for k in total:
            total[k] += s[k]
        _row(layer, s)
    _row("TOTAL", total)

    if problems:
        print("\nCas à examiner :")
        for label, d, expected in problems:
            print(f"  {label:<16} {d.table_name + '.' + d.column_name:<42} détecté={d.pii_type or '-':<14}"
                  f"attendu={expected or '-':<14} score={d.confidence:<5} {d.evidence}")


def _row(name, s):
    precision = s["tp"] / (s["tp"] + s["fp"]) if s["tp"] + s["fp"] else 0
    recall = s["tp"] / (s["tp"] + s["fn"]) if s["tp"] + s["fn"] else 0
    print(f"{name:<10}{s['tp']:>13}{s['fp']:>15}{s['fn']:>10}{s['review']:>12}{precision:>11.0%}{recall:>8.0%}")


if __name__ == "__main__":
    main()
