-- ---------------------------------------------------------------------------
-- Points de prévision quotidiens : la VRAIE courbe Prophet, jour par jour.
--
-- silver.forecasts ne stocke que le résumé d'un run (date de rupture, proba).
-- Cette table matérialise la trajectoire complète du stock prévu
-- (médiane + bande de confiance 80 %) pour que Streamlit affiche la courbe
-- réellement calculée par le modèle, pas une reconstruction.
--
-- Écrite par ml/shortage_forecast.py à chaque run (nightly via Dagster).
-- Lue par dashboards/streamlit/lib/live_data.py (shortage_forecast_curve).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gold.forecast_points (
    forecast_ts        TIMESTAMPTZ     NOT NULL,   -- horodatage du run Prophet
    site_id            TEXT            NOT NULL,
    drug_id            TEXT            NOT NULL,
    ds                 DATE            NOT NULL,   -- jour prévu
    stock_yhat         NUMERIC(12, 1),             -- stock restant prévu (médiane)
    stock_yhat_lower   NUMERIC(12, 1),             -- borne basse (demande haute)
    stock_yhat_upper   NUMERIC(12, 1),             -- borne haute (demande basse)
    model_version      TEXT,
    PRIMARY KEY (site_id, drug_id, forecast_ts, ds)
);

CREATE INDEX IF NOT EXISTS ix_forecast_points_drug
    ON gold.forecast_points (drug_id, forecast_ts DESC);

-- Les points du DERNIER run par (site, médicament) : ce que l'UI consomme.
CREATE OR REPLACE VIEW gold.v_forecast_points_latest AS
SELECT
    p.site_id,
    p.drug_id,
    p.forecast_ts,
    p.ds,
    p.stock_yhat,
    p.stock_yhat_lower,
    p.stock_yhat_upper,
    p.model_version
FROM gold.forecast_points AS p
INNER JOIN (
    SELECT
        site_id,
        drug_id,
        MAX(forecast_ts) AS forecast_ts
    FROM gold.forecast_points
    GROUP BY site_id, drug_id
) AS last
    ON p.site_id = last.site_id
    AND p.drug_id = last.drug_id
    AND p.forecast_ts = last.forecast_ts;

-- Rétention : on garde 180 jours de runs (assez pour le backtest visuel).
DELETE FROM gold.forecast_points
WHERE forecast_ts < NOW() - INTERVAL '180 days';
