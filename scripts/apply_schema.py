"""Applique tous les fichiers SQL sous sql/timescale/ à la base cible.

À lancer dans le conteneur (`make schema`), via le service db-init du
docker-compose, ou contre un Postgres distant en pointant les variables
d'environnement TIMESCALE_* dessus. Tous les DDL sont idempotents
(IF NOT EXISTS) : rejouer le script sur une base déjà initialisée est sûr,
c'est ce qui permet d'ajouter une table au schéma sans recréer le volume.

Les statements sont exécutés un par un : les agrégats continus TimescaleDB
(CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)) refusent de
tourner dans le bloc de transaction implicite que crée un execute() sur le
fichier entier.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from loguru import logger
from psycopg import conninfo

SQL_DIR = Path(__file__).resolve().parents[1] / "sql" / "timescale"


def _dsn() -> str:
    # make_conninfo échappe correctement les valeurs et évite de promener
    # le mot de passe dans une f-string loggable.
    return conninfo.make_conninfo(
        host=os.environ["TIMESCALE_HOST"],
        port=os.environ.get("TIMESCALE_PORT", "5432"),
        dbname=os.environ["TIMESCALE_DB"],
        user=os.environ["TIMESCALE_USER"],
        password=os.environ["TIMESCALE_PASSWORD"],
    )


def _only_comments(stmt: str) -> bool:
    return all(
        line.strip().startswith("--") or not line.strip()
        for line in stmt.splitlines()
    )


def _statements(sql: str) -> list[str]:
    """Découpe un fichier SQL en statements exécutables.

    Le découpage ne coupe que sur les ';' réellement terminateurs : ceux
    situés dans un commentaire `--` ou dans une chaîne entre quotes sont
    ignorés (le DDL contient des commentaires en français avec des
    points-virgules typographiques). Pas de gestion PL/pgSQL ni de
    dollar-quoting : le schéma du projet n'en utilise pas.
    """
    out: list[str] = []
    buf: list[str] = []
    in_string = in_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_comment:
            buf.append(ch)
            if ch == "\n":
                in_comment = False
        elif in_string:
            buf.append(ch)
            if ch == "'":
                in_string = False
        elif ch == "'":
            in_string = True
            buf.append(ch)
        elif ch == "-" and sql[i:i + 2] == "--":
            in_comment = True
            buf.append(ch)
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt and not _only_comments(stmt):
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    stmt = "".join(buf).strip()
    if stmt and not _only_comments(stmt):
        out.append(stmt)
    return out


def main() -> None:
    load_dotenv()
    files = sorted(SQL_DIR.glob("*.sql"))
    if not files:
        raise SystemExit(f"No SQL files found in {SQL_DIR}")

    with psycopg.connect(_dsn(), autocommit=True) as conn:
        for f in files:
            logger.info(f"applying {f.name}")
            for stmt in _statements(f.read_text()):
                with conn.cursor() as cur:
                    cur.execute(stmt)
    logger.success(f"applied {len(files)} SQL files")


if __name__ == "__main__":
    main()
