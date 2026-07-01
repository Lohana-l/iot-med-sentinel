"""Requêtes de features pour le modèle de prévision des ruptures."""
from __future__ import annotations

import pandas as pd

from ingestion.utils.db import pg_conn

# ---------------------------------------------------------------------------
# Historique quotidien de dispensation par (site, médicament)
# ---------------------------------------------------------------------------
_HIST_SQL = """
    SELECT
        DATE_TRUNC('day', observed_at)::DATE AS ds,
        site_id,
        drug_id,
        dispensed_doses                      AS y
    FROM silver.dispensing_daily
    WHERE site_id = %(site)s
      AND drug_id = %(drug)s
      AND observed_at >= NOW() - INTERVAL '400 days'
    ORDER BY ds
"""


def load_history(site_id: str, drug_id: str) -> pd.DataFrame:
    """Retourne un DataFrame deux colonnes (ds, y) prêt pour Prophet."""
    with pg_conn() as conn:
        df = pd.read_sql(_HIST_SQL, conn, params={"site": site_id, "drug": drug_id})
    return df[["ds", "y"]]


# ---------------------------------------------------------------------------
# Stock actuel (hors lots suspects)
# ---------------------------------------------------------------------------
_STOCK_SQL = """
    SELECT COALESCE(SUM(doses), 0) AS doses_available
    FROM silver.inventory_lots
    WHERE site_id   = %(site)s
      AND drug_id   = %(drug)s
      AND suspect   = FALSE
      AND expires_at > NOW()
"""


def current_stock(site_id: str, drug_id: str) -> int:
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(_STOCK_SQL, {"site": site_id, "drug": drug_id})
        row = cur.fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Signaux FDA / ANSM : boost amont en cas de pénurie
# ---------------------------------------------------------------------------
def external_shortage_signal(drug_id: str) -> float:
    """Retourne un facteur de boost [0, 1] : 1.0 = pas de signal, jusqu'à 1.5 si FDA+ANSM rouge."""
    sql = """
        SELECT source, status
        FROM silver.shortage_signals
        WHERE drug_id = %s
          AND signal_ts >= NOW() - INTERVAL '30 days'
    """
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (drug_id,))
        rows = cur.fetchall()

    if not rows:
        return 1.0
    weights = {"fda": 0.2, "ansm": 0.2, "ema": 0.15}
    factor = 1.0 + sum(weights.get(src, 0.05) for src, _ in rows)
    return min(factor, 1.5)
