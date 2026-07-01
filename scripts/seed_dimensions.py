"""Seed des référentiels : la pièce qui relie la télémétrie au reste du pipeline.

Le simulateur produit des événements pour des frigos SITE-xx-Fyy, mais les
requêtes du dashboard joignent silver.dim_sites / dim_fridges / dim_drugs et
lisent silver.inventory_lots et silver.dispensing_daily. Sans ces référentiels,
chaque JOIN retourne zéro ligne et l'UI retombe sur le mock.

Ce script insère, de façon idempotente (ON CONFLICT DO NOTHING) :

* les sites et frigos, avec EXACTEMENT les identifiants du simulateur
  (simulator.fleet.make_site_id / make_fridge_id, source unique de vérité) ;
* le référentiel médicaments chaîne du froid (codes ATC réels) ;
* des lots d'inventaire plausibles répartis dans les frigos ;
* 270 jours d'historique de dispensation quotidienne avec saisonnalité
  hebdomadaire, de quoi entraîner Prophet (60 j minimum) et lancer les
  backtests walk-forward (120 j minimum).

Tout est déterministe (graine fixe) : relancer le script ne change rien,
le relancer après un `make nuke` reconstruit le même monde.

Usage :
    python -m scripts.seed_dimensions
"""
from __future__ import annotations

import random
from datetime import UTC, datetime, time, timedelta

from loguru import logger

from ingestion.config import settings
from ingestion.utils.db import pg_conn
from simulator.fleet import make_fridge_id, make_site_id

_SEED = 42

# Libellés de sites : les six premiers reprennent le mock pour que la bascule
# démo vers live soit visuellement transparente, les suivants complètent la flotte.
# Coordonnées réelles des établissements : elles servent au calcul de distance
# des candidats de redistribution dans le brief clinique.
_SITE_NAMES = [
    ("CHU Lyon-Sud",                "Auvergne-Rhône-Alpes", 45.6960, 4.7880),
    ("CHU Lyon-Nord",               "Auvergne-Rhône-Alpes", 45.8030, 4.8260),
    ("Hôpital Cochin",              "Île-de-France",        48.8390, 2.3410),
    ("CHU Bordeaux Pellegrin",      "Nouvelle-Aquitaine",   44.8260, -0.6040),
    ("CHU Toulouse Rangueil",       "Occitanie",            43.5610, 1.4520),
    ("Pharmacie Centrale Grenoble", "Auvergne-Rhône-Alpes", 45.1750, 5.7280),
    ("CHU Lille Salengro",          "Hauts-de-France",      50.6090, 3.0340),
    ("CHU Nantes Hôtel-Dieu",       "Pays de la Loire",     47.2120, -1.5540),
]

# Médicaments chaîne du froid : mêmes couples (nom, ATC) que le contrat mock.
_DRUGS = [
    ("J07BB02", "Influenza vaccine (inactivated)", "Vaccin"),
    ("A10AE04", "Insulin glargine",                "Antidiabétique"),
    ("J01CR02", "Amoxicillin/clavulanate",         "Antibiotique"),
    ("J07BD52", "MMR vaccine",                     "Vaccin"),
    ("A10AE05", "Insulin detemir",                 "Antidiabétique"),
]

_HISTORY_DAYS = 270


def _seed_sites_and_fridges(cur, n_sites: int, fridges_per_site: int) -> None:
    for s in range(n_sites):
        site_id = make_site_id(s)
        name, region, lat, lon = _SITE_NAMES[s % len(_SITE_NAMES)]
        cur.execute(
            """
            INSERT INTO silver.dim_sites
                (site_id, site_name, country, region, latitude, longitude)
            VALUES (%s, %s, 'FR', %s, %s, %s)
            ON CONFLICT (site_id) DO NOTHING
            """,
            (site_id, name, region, lat, lon),
        )
        for f in range(fridges_per_site):
            cur.execute(
                """
                INSERT INTO silver.dim_fridges
                    (fridge_id, site_id, model, target_low_c, target_high_c)
                VALUES (%s, %s, 'Liebherr MKv 3910', 2.0, 8.0)
                ON CONFLICT (fridge_id) DO NOTHING
                """,
                (make_fridge_id(site_id, f), site_id),
            )


def _seed_drugs(cur) -> None:
    for drug_id, name, category in _DRUGS:
        cur.execute(
            """
            INSERT INTO silver.dim_drugs
                (drug_id, generic_name, therapeutic_cat, cold_chain)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (drug_id) DO NOTHING
            """,
            (drug_id, name, category),
        )


def _seed_inventory(cur, n_sites: int, fridges_per_site: int,
                    rng: random.Random) -> int:
    """Deux à quatre lots par frigo, répartis sur le référentiel médicaments.

    Les quantités sont calibrées pour que certaines paires (site, médicament)
    soient tendues (10 à 20 jours de stock) : le modèle de prévision a ainsi
    de vraies ruptures à détecter dans son horizon de 30 jours.
    """
    now = datetime.now(UTC)
    n = 0
    for s in range(n_sites):
        site_id = make_site_id(s)
        for f in range(fridges_per_site):
            fridge_id = make_fridge_id(site_id, f)
            for _ in range(rng.randint(2, 4)):
                drug_id, _name, _cat = rng.choice(_DRUGS)
                # Stock serré une fois sur trois, confortable sinon.
                doses = rng.randint(120, 300) if rng.random() < 0.34 \
                    else rng.randint(400, 900)
                received = now - timedelta(days=rng.randint(5, 60))
                lot_id = f"LOT-{site_id}-{fridge_id[-3:]}-{n:04d}"
                cur.execute(
                    """
                    INSERT INTO silver.inventory_lots
                        (lot_id, drug_id, site_id, fridge_id, doses,
                         received_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (lot_id) DO NOTHING
                    """,
                    (lot_id, drug_id, site_id, fridge_id, doses,
                     received, received + timedelta(days=rng.randint(180, 540))),
                )
                n += 1
    return n


def _seed_dispensing_history(cur, n_sites: int, rng: random.Random) -> int:
    """Historique quotidien par (site, médicament) : tendance douce,
    saisonnalité hebdomadaire marquée (creux le week-end), bruit gaussien.

    Insertion en batch via executemany ; l'horodatage est fixé à midi UTC pour
    que DATE_TRUNC('day', observed_at) (ml/features.py) tombe toujours juste.
    """
    today = datetime.now(UTC).date()
    rows: list[tuple] = []
    for s in range(n_sites):
        site_id = make_site_id(s)
        for drug_id, _name, _cat in _DRUGS:
            base = rng.uniform(8.0, 22.0)            # demande moyenne du couple
            trend = rng.uniform(-0.004, 0.008)       # dérive lente sur 9 mois
            for i in range(_HISTORY_DAYS):
                d = today - timedelta(days=_HISTORY_DAYS - i)
                weekday_factor = 0.45 if d.weekday() >= 5 else 1.0
                demand = base * (1 + trend * i) * weekday_factor \
                    + rng.gauss(0, base * 0.12)
                rows.append((
                    datetime.combine(d, time(12, 0), tzinfo=UTC),
                    site_id, drug_id, max(0, round(demand)),
                ))
    cur.executemany(
        """
        INSERT INTO silver.dispensing_daily
            (observed_at, site_id, drug_id, dispensed_doses)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (site_id, drug_id, observed_at) DO NOTHING
        """,
        rows,
    )
    return len(rows)


def main() -> None:
    cfg = settings()
    rng = random.Random(_SEED)
    with pg_conn() as conn, conn.cursor() as cur:
        _seed_sites_and_fridges(cur, cfg.simulator_sites,
                                cfg.simulator_fridges_per_site)
        _seed_drugs(cur)
        n_lots = _seed_inventory(cur, cfg.simulator_sites,
                                 cfg.simulator_fridges_per_site, rng)
        n_hist = _seed_dispensing_history(cur, cfg.simulator_sites, rng)
    logger.success(
        f"seed terminé : {cfg.simulator_sites} sites, "
        f"{cfg.simulator_sites * cfg.simulator_fridges_per_site} frigos, "
        f"{len(_DRUGS)} médicaments, {n_lots} lots, "
        f"{n_hist} lignes de dispensation"
    )


if __name__ == "__main__":
    main()
