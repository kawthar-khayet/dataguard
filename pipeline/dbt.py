"""Lance dbt depuis Python, avec les variables d'environnement du fichier .env."""
from pathlib import Path

from dbt.cli.main import dbtRunner, dbtRunnerResult
from dotenv import load_dotenv

DBT_DIR = str(Path(__file__).resolve().parent.parent / "dbt")


def run_dbt(args: list[str]) -> dbtRunnerResult:
    load_dotenv()   # dbt lit le mot de passe et le sel de hachage dans l'environnement
    return dbtRunner().invoke(args + ["--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR])
