-- ---------------------------------------------------------------------------
-- Agrégats continus : rollups de télémétrie sur 5 minutes pré-calculés.
-- Moins coûteux que les vues matérialisées ; ils se rafraîchissent de façon incrémentale.
-- ---------------------------------------------------------------------------

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.telemetry_5m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket(INTERVAL '5 minutes', event_ts)    AS bucket,
    fridge_id,
    site_id,
    avg(temperature_c)::NUMERIC(5,2)               AS avg_temp_c,
    min(temperature_c)::NUMERIC(5,2)               AS min_temp_c,
    max(temperature_c)::NUMERIC(5,2)               AS max_temp_c,
    avg(humidity_pct)::NUMERIC(5,2)                AS avg_humidity_pct,
    bool_or(door_open)                             AS door_opened,
    count(*)                                       AS n_samples
FROM silver.telemetry_raw
GROUP BY bucket, fridge_id, site_id;

-- Maintient le CAGG à jour ; la fenêtre temps-réel couvre les 5 dernières minutes de données brutes.
SELECT add_continuous_aggregate_policy(
    'silver.telemetry_5m',
    start_offset => INTERVAL '1 day',
    end_offset   => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);

-- --- Rétention : supprime les échantillons bruts de plus de 90 jours ----
SELECT add_retention_policy(
    'silver.telemetry_raw',
    INTERVAL '90 days',
    if_not_exists => TRUE
);
