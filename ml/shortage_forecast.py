"""
Prévision de rupture basée sur Prophet.

À partir de l'historique de dispensation pour (site, médicament) et du stock actuel
(hors lots suspects), prédit la date de rupture et une probabilité associée.
Écrit les résultats dans silver.forecasts.

Le modèle est volontairement simple : une instance Prophet par (site, médicament).
En production on partagerait la saisonnalité entre sites via un modèle hiérarchique
ou on passerait à StatsForecast / NeuralForecast, mais c'est suffisant pour le
périmètre de ce projet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd
from loguru import logger
from prophet import Prophet

from ingestion.utils.db import pg_conn
from ml.features import current_stock, external_shortage_signal, load_history

MODEL_VERSION = "prophet-0.1"
HORIZON_DAYS = 30
MIN_HISTORY_DAYS = 60


@dataclass
class ForecastResult:
    site_id: str
    drug_id: str
    forecast_ts: datetime
    predicted_stockout_on: date | None
    shortage_prob: float
    doses_remaining: int
    model_version: str
    # Trajectoire quotidienne du stock prévu (ds, stock_yhat, lower, upper) :
    # matérialisée dans gold.forecast_points pour que l'UI affiche la VRAIE
    # courbe Prophet, pas une reconstruction.
    points: pd.DataFrame | None = None


def _predict_cumulative_demand(history: pd.DataFrame, horizon: int) -> pd.DataFrame:
    m = Prophet(
        growth="linear",
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
        seasonality_mode="multiplicative",
        interval_width=0.8,
    )
    m.fit(history.rename(columns={"ds": "ds", "y": "y"}))
    future = m.make_future_dataframe(periods=horizon, include_history=False)
    fcst = m.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
    fcst["yhat"] = fcst["yhat"].clip(lower=0)
    fcst["yhat_lower"] = fcst["yhat_lower"].clip(lower=0)
    fcst["yhat_upper"] = fcst["yhat_upper"].clip(lower=0)
    fcst["cum_yhat"] = fcst["yhat"].cumsum()
    fcst["cum_yhat_lower"] = fcst["yhat_lower"].cumsum()
    fcst["cum_yhat_upper"] = fcst["yhat_upper"].cumsum()
    return fcst


def _stockout_date(fcst: pd.DataFrame, doses: int, col: str = "cum_yhat") -> date | None:
    crossed = fcst[fcst[col] >= doses]
    if crossed.empty:
        return None
    return crossed["ds"].iloc[0].date()


def forecast_one(site_id: str, drug_id: str) -> ForecastResult | None:
    history = load_history(site_id, drug_id)
    if len(history) < MIN_HISTORY_DAYS:
        logger.info(f"skip {site_id}/{drug_id}: only {len(history)} days of history")
        return None

    stock = current_stock(site_id, drug_id)
    signal_boost = external_shortage_signal(drug_id)

    fcst = _predict_cumulative_demand(history, HORIZON_DAYS)
    # Applique le boost du signal amont de façon multiplicative sur la courbe de demande.
    fcst["cum_yhat"] *= signal_boost
    fcst["cum_yhat_lower"] *= signal_boost
    fcst["cum_yhat_upper"] *= signal_boost

    p50_stockout = _stockout_date(fcst, stock, "cum_yhat")

    # probabilité de rupture dans l'horizon : proportion des jours de l'horizon où
    # la bande supérieure à 80 % a déjà dépassé le stock.
    prob = float((fcst["cum_yhat_upper"] >= stock).mean())

    # Trajectoire du stock restant : stock - demande cumulée prévue.
    # Attention au croisement des bandes : une demande HAUTE donne un stock BAS.
    points = pd.DataFrame({
        "ds":               fcst["ds"].dt.date,
        "stock_yhat":       (stock - fcst["cum_yhat"]).clip(lower=0).round(1),
        "stock_yhat_lower": (stock - fcst["cum_yhat_upper"]).clip(lower=0).round(1),
        "stock_yhat_upper": (stock - fcst["cum_yhat_lower"]).clip(lower=0).round(1),
    })

    return ForecastResult(
        site_id=site_id,
        drug_id=drug_id,
        forecast_ts=datetime.now(UTC),
        predicted_stockout_on=p50_stockout,
        shortage_prob=round(prob, 4),
        doses_remaining=int(stock),
        model_version=MODEL_VERSION,
        points=points,
    )


def _pairs_to_forecast() -> list[tuple[str, str]]:
    """Toutes les paires (site, médicament) ayant un lot d'inventaire actif, non suspect."""
    sql = """
        SELECT DISTINCT site_id, drug_id
        FROM silver.inventory_lots
        WHERE expires_at > NOW()
    """
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return [tuple(r) for r in cur.fetchall()]


def _write(results: list[ForecastResult]) -> None:
    if not results:
        return
    sql = """
        INSERT INTO silver.forecasts
          (forecast_ts, site_id, drug_id, horizon_days,
           predicted_stockout_on, shortage_prob, doses_remaining, model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (site_id, drug_id, forecast_ts) DO NOTHING
    """
    rows = [
        (
            r.forecast_ts, r.site_id, r.drug_id, HORIZON_DAYS,
            r.predicted_stockout_on, r.shortage_prob,
            r.doses_remaining, r.model_version,
        )
        for r in results
    ]
    with pg_conn() as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)
    logger.success(f"wrote {len(rows)} forecast rows")


def _write_points(results: list[ForecastResult]) -> None:
    """Matérialise la courbe quotidienne dans gold.forecast_points.

    C'est ce qui permet à Streamlit (et Grafana) d'afficher la vraie
    trajectoire Prophet avec sa bande de confiance, run après run.
    """
    rows = []
    for r in results:
        if r.points is None or r.points.empty:
            continue
        for p in r.points.itertuples(index=False):
            rows.append((
                r.forecast_ts, r.site_id, r.drug_id, p.ds,
                p.stock_yhat, p.stock_yhat_lower, p.stock_yhat_upper,
                r.model_version,
            ))
    if not rows:
        return
    sql = """
        INSERT INTO gold.forecast_points
          (forecast_ts, site_id, drug_id, ds,
           stock_yhat, stock_yhat_lower, stock_yhat_upper, model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (site_id, drug_id, forecast_ts, ds) DO NOTHING
    """
    with pg_conn() as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)
    logger.success(f"wrote {len(rows)} forecast points")


def run() -> int:
    pairs = _pairs_to_forecast()
    logger.info(f"forecasting {len(pairs)} (site, drug) pairs")
    results = []
    for site, drug in pairs:
        try:
            r = forecast_one(site, drug)
            if r:
                results.append(r)
        except Exception:
            logger.exception(f"forecast failed for {site}/{drug}")
    _write(results)
    _write_points(results)
    return len(results)


if __name__ == "__main__":
    run()
