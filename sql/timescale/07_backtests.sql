-- ---------------------------------------------------------------------------
-- Backtests walk-forward du modèle de prévision (ml/backtest.py).
-- Le DDL vit ici, avec le reste du schéma versionné : le code applicatif
-- ne crée plus de table à la volée.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.forecast_backtests (
    run_ts          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    site_id         TEXT            NOT NULL,
    drug_id         TEXT            NOT NULL,
    fold            INTEGER         NOT NULL,
    mape            NUMERIC(6, 3),
    coverage80      NUMERIC(5, 3),
    PRIMARY KEY (site_id, drug_id, fold, run_ts)
);

CREATE INDEX IF NOT EXISTS ix_backtests_pair_time
    ON silver.forecast_backtests (site_id, drug_id, run_ts DESC);
