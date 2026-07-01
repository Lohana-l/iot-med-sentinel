-- ---------------------------------------------------------------------------
-- Vues gold : celles que Streamlit + Grafana + Prophet lisent.
-- Vues SQL simples pour l'instant ; à migrer vers dbt si le projet grandit.
-- ---------------------------------------------------------------------------

-- Stock actuel par (site, médicament), lots suspects exclus.
CREATE OR REPLACE VIEW gold.v_stock_current AS
SELECT
    site_id,
    drug_id,
    SUM(doses)                               AS doses_available,
    SUM(CASE WHEN suspect THEN doses ELSE 0 END) AS doses_suspect,
    COUNT(*)                                 AS n_lots
FROM silver.inventory_lots
WHERE expires_at > NOW()
GROUP BY site_id, drug_id;

-- Flux d'alertes actives pour la page alertes Streamlit.
CREATE OR REPLACE VIEW gold.v_alerts_active AS
SELECT
    a.alert_id,
    a.opened_at,
    a.site_id,
    a.fridge_id,
    a.severity,
    a.peak_temp_c,
    a.duration_sec,
    s.site_name,
    f.model AS fridge_model
FROM silver.alerts AS a
INNER JOIN silver.dim_sites AS s   ON a.site_id   = s.site_id
INNER JOIN silver.dim_fridges AS f ON a.fridge_id = f.fridge_id
WHERE a.closed_at IS NULL
   OR a.closed_at > NOW() - INTERVAL '7 days'
ORDER BY a.opened_at DESC;

-- Dernière prévision par (site, médicament).
CREATE OR REPLACE VIEW gold.v_forecast_latest AS
SELECT DISTINCT ON (site_id, drug_id)
    site_id,
    drug_id,
    forecast_ts,
    horizon_days,
    predicted_stockout_on,
    shortage_prob,
    doses_remaining,
    model_version
FROM silver.forecasts
ORDER BY site_id ASC, drug_id ASC, forecast_ts DESC;
