"""
DataGuard — orchestration du pipeline de bout en bout.

    sources    simule les systèmes de l'opérateur (CRM, facturation, réseau, centre d'appel)
    ingest     charge tout, tel quel, dans le schéma raw
    transform  dbt : staging (nettoyage, dédoublonnage) + marts (tables métier) + tests
    scan       découverte → détection → catalogue → propositions de politiques
    ─── validation humaine dans l'interface Streamlit ───
    protect    anonymisation + vues masquées + tests de non-fuite + contrôle d'accès

Exemples :
    .venv\\Scripts\\python.exe -W ignore -m pipeline.run all       (sources → scan)
    .venv\\Scripts\\python.exe -W ignore -m pipeline.run transform
    .venv\\Scripts\\python.exe -W ignore -m pipeline.run protect
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def step_sources():
    subprocess.run([sys.executable, "-W", "ignore", str(ROOT / "generator" / "sources.py")], check=True)

def step_ingest():
    from ingestion import load_raw
    load_raw.main()

def step_transform():
    from pipeline.dbt import run_dbt
    if not run_dbt(["build", "--select", "+tag:transform"]).success:
        sys.exit("❌ transform : des modèles ou des tests dbt ont échoué")

def step_scan():
    from scanner import run_scan
    run_scan.main()

def step_protect():
    from scanner import protect
    sys.exit(protect.main())


STEPS = {"sources": step_sources, "ingest": step_ingest, "transform": step_transform,
         "scan": step_scan, "protect": step_protect}
ALL = ["sources", "ingest", "transform", "scan"]   # protect vient APRÈS la validation humaine


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    asked = sys.argv[1:] or ["all"]
    names = ALL if asked == ["all"] else asked
    for name in names:
        if name not in STEPS:
            sys.exit(f"Étape inconnue : {name}. Choix : {', '.join(STEPS)} ou all")
        print(f"\n══════ {name} ══════", flush=True)
        STEPS[name]()
    if asked == ["all"]:
        print("\n➜ Valide maintenant les politiques dans l'interface, puis lance l'étape « protect ».")


if __name__ == "__main__":
    main()
