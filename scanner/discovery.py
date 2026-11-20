"""
DataGuard — étape 1 du scanner : découverte et profilage.

1. Découverte : lit le catalogue système `information_schema` pour lister
   toutes les tables et colonnes du schéma `source`, avec leur type.
2. Profilage : pour chaque colonne, calcule des statistiques
   (taux de valeurs nulles, taux de valeurs distinctes, longueur moyenne)
   et prélève un échantillon de valeurs.

Règle de sécurité : l'échantillon reste EN MÉMOIRE (il sert à la détection),
il n'est jamais écrit en base. Seules les statistiques sont enregistrées
dans `governance.column_profile`. Sinon, DataGuard créerait lui-même une
nouvelle copie des données personnelles qu'il est censé protéger.

Lancer seul :  .venv\\Scripts\\python.exe -m scanner.discovery
"""
from dataclasses import dataclass, field

from psycopg import sql

from scanner.db import connect

SCHEMA = "source"
SAMPLE_SIZE = 200


@dataclass
class ColumnProfile:
    table_name: str
    column_name: str
    data_type: str
    n_rows: int = 0
    null_ratio: float = 0.0
    distinct_ratio: float = 0.0
    avg_length: float = 0.0
    sample: list[str] = field(default_factory=list, repr=False)  # en mémoire uniquement


def discover_columns(conn) -> list[ColumnProfile]:
    """Étape 1 : liste les colonnes via information_schema (aucune donnée lue)."""
    rows = conn.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
        """,
        (SCHEMA,),
    ).fetchall()
    return [ColumnProfile(t, c, d) for t, c, d in rows]


def profile_column(conn, col: ColumnProfile) -> ColumnProfile:
    """Étape 2 : statistiques + échantillon pour une colonne."""
    # sql.Identifier protège les noms de tables/colonnes (pas d'injection SQL)
    table = sql.Identifier(SCHEMA, col.table_name)
    column = sql.Identifier(col.column_name)

    stats = sql.SQL("""
        SELECT count(*),
               count(*) - count({c}),
               count(DISTINCT {c}),
               coalesce(avg(length({c}::text)), 0)
        FROM {t}
    """).format(c=column, t=table)
    n_rows, n_nulls, n_distinct, avg_len = conn.execute(stats).fetchone()

    col.n_rows = n_rows
    col.null_ratio = round(n_nulls / n_rows, 3) if n_rows else 0.0
    col.distinct_ratio = round(n_distinct / n_rows, 3) if n_rows else 0.0
    col.avg_length = round(float(avg_len), 1)

    # Échantillon aléatoire. Sur une très grosse table on utiliserait plutôt
    # TABLESAMPLE pour éviter de trier toute la table.
    sample = sql.SQL("""
        SELECT {c}::text FROM {t}
        WHERE {c} IS NOT NULL
        ORDER BY random() LIMIT {n}
    """).format(c=column, t=table, n=sql.Literal(SAMPLE_SIZE))
    col.sample = [r[0] for r in conn.execute(sample).fetchall()]
    return col


def save_profiles(conn, profiles: list[ColumnProfile]) -> int:
    """Enregistre les statistiques (jamais l'échantillon) et renvoie l'id du scan."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS governance.scan_run (
            run_id     SERIAL PRIMARY KEY,
            started_at TIMESTAMPTZ DEFAULT now(),
            n_columns  INT
        );
        CREATE TABLE IF NOT EXISTS governance.column_profile (
            run_id         INT REFERENCES governance.scan_run,
            table_name     TEXT,
            column_name    TEXT,
            data_type      TEXT,
            n_rows         INT,
            null_ratio     REAL,
            distinct_ratio REAL,
            avg_length     REAL,
            PRIMARY KEY (run_id, table_name, column_name)
        );
    """)
    run_id = conn.execute(
        "INSERT INTO governance.scan_run (n_columns) VALUES (%s) RETURNING run_id",
        (len(profiles),),
    ).fetchone()[0]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO governance.column_profile VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [(run_id, p.table_name, p.column_name, p.data_type, p.n_rows,
              p.null_ratio, p.distinct_ratio, p.avg_length) for p in profiles],
        )
    return run_id


def run() -> tuple[int, list[ColumnProfile]]:
    with connect() as conn:
        profiles = [profile_column(conn, c) for c in discover_columns(conn)]
        run_id = save_profiles(conn, profiles)
    return run_id, profiles


if __name__ == "__main__":
    run_id, profiles = run()
    print(f"Scan n°{run_id} : {len(profiles)} colonnes découvertes dans le schéma '{SCHEMA}'\n")
    print(f"{'table':<14}{'colonne':<18}{'type':<10}{'lignes':>7}{'nulls':>7}"
          f"{'distinct':>9}{'long.':>7}  exemple")
    for p in profiles:
        exemple = (p.sample[0] if p.sample else "")[:30]
        print(f"{p.table_name:<14}{p.column_name:<18}{p.data_type[:9]:<10}{p.n_rows:>7}"
              f"{p.null_ratio:>7}{p.distinct_ratio:>9}{p.avg_length:>7}  {exemple}")
