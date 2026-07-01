"""
Backtest walk-forward pour le modèle de prévision des ruptures.

Découpe les 90 derniers jours d'historique en 6 × 15 jours de folds de test. Pour chaque
fold, entraîne sur tout ce qui précède et évalue le MAPE + la précision directionnelle
des ruptures sur le fold.

Les résultats sont écrits dans silver.forecast_backtests, dont le DDL est
versionné avec le reste du schéma (sql/timescale/07_backtests.sql) : le code
applicatif ne crée plus de table à la volée.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger
from prophet import Prophet

from ingestion.utils.db import pg_conn
from ml.features import load_history

FOLDS = 6
FOLD_DAYS = 15
MIN_HISTORY_DAYS = 120


def _score_fold(history: pd.DataFrame, fold_start: pd.Timestamp, fold_days: int) -> dict:
    train = history[history["ds"] < fold_start]
    test  = history[(history["ds"] >= fold_start) &
                    (history["ds"] <  fold_start + pd.Timedelta(days=fold_days))]
    if train.empty or test.empty:
        return {}
    m = Prophet(daily_seasonality=False, weekly_seasonality=True,
                yearly_seasonality=True, interval_width=0.8)
    m.fit(train)
    fut = m.make_future_dataframe(periods=fold_days, include_history=False)
    fcst = m.predict(fut)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
    merged = fcst.merge(test, on="ds", how="inner")
    if merged.empty:
        return {}
    mape = float(np.mean(np.abs(merged["y"] - merged["yhat"]) /
                         np.maximum(merged["y"], 1.0)))
    coverage = float(np.mean((merged["y"] >= merged["yhat_lower"]) &
                             (merged["y"] <= merged["yhat_upper"])))
    return {"mape": mape, "coverage80": coverage}


def run(site_id: str, drug_id: str) -> pd.DataFrame:
    history = load_history(site_id, drug_id)
    if len(history) < MIN_HISTORY_DAYS:
        logger.info(f"skip backtest {site_id}/{drug_id}: only {len(history)} days")
        return pd.DataFrame()

    history["ds"] = pd.to_datetime(history["ds"])
    last = history["ds"].max()
    rows = []
    for f in range(FOLDS):
        fold_start = last - pd.Timedelta(days=FOLD_DAYS * (FOLDS - f))
        scores = _score_fold(history, fold_start, FOLD_DAYS)
        if scores:
            rows.append({"site_id": site_id, "drug_id": drug_id,
                         "fold": f, **scores})
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    sql = """
        INSERT INTO silver.forecast_backtests
          (site_id, drug_id, fold, mape, coverage80)
        VALUES (%s, %s, %s, %s, %s)
    """
    with pg_conn() as conn, conn.cursor() as cur:
        cur.executemany(sql, df[["site_id", "drug_id", "fold",
                                 "mape", "coverage80"]].values.tolist())
    logger.success(f"backtest {site_id}/{drug_id}: "
                   f"MAPE={df['mape'].mean():.2%} coverage={df['coverage80'].mean():.2%}")
    return df
