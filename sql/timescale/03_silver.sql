-- ---------------------------------------------------------------------------
-- Silver : tables typées alimentées soit par :
--  • insertion directe depuis le consumer streaming (télémétrie / alertes)
--  • vues de style dbt posées sur le bronze (dimensions médicament)
-- ---------------------------------------------------------------------------

-- --- Dimensions -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.dim_sites (
    site_id         TEXT            PRIMARY KEY,
    site_name       TEXT            NOT NULL,
    country         CHAR(2)         NOT NULL,
    region          TEXT,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS silver.dim_fridges (
    fridge_id       TEXT            PRIMARY KEY,
    site_id         TEXT            NOT NULL REFERENCES silver.dim_sites(site_id),
    model           TEXT,
    target_low_c    NUMERIC(4,1)    NOT NULL DEFAULT 2.0,
    target_high_c   NUMERIC(4,1)    NOT NULL DEFAULT 8.0
);

CREATE TABLE IF NOT EXISTS silver.dim_drugs (
    drug_id         TEXT            PRIMARY KEY,    -- code ATC
    generic_name    TEXT            NOT NULL,
    therapeutic_cat TEXT,
    cold_chain      BOOLEAN         NOT NULL DEFAULT FALSE
);

-- --- Inventaire (faible mouvement) ---------------------------------------
CREATE TABLE IF NOT EXISTS silver.inventory_lots (
    lot_id          TEXT            PRIMARY KEY,
    drug_id         TEXT            NOT NULL REFERENCES silver.dim_drugs(drug_id),
    site_id         TEXT            NOT NULL REFERENCES silver.dim_sites(site_id),
    fridge_id       TEXT            REFERENCES silver.dim_fridges(fridge_id),
    doses           INTEGER         NOT NULL,
    received_at     TIMESTAMPTZ     NOT NULL,
    expires_at      TIMESTAMPTZ     NOT NULL,
    suspect         BOOLEAN         NOT NULL DEFAULT FALSE,
    suspect_reason  TEXT,
    suspect_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_lots_site_drug
    ON silver.inventory_lots (site_id, drug_id);

-- --- Hypertable de télémétrie ---------------------------------------------
CREATE TABLE IF NOT EXISTS silver.telemetry_raw (
    event_ts        TIMESTAMPTZ     NOT NULL,
    fridge_id       TEXT            NOT NULL,
    site_id         TEXT            NOT NULL,
    temperature_c   NUMERIC(5,2)    NOT NULL,
    humidity_pct    NUMERIC(5,2),
    door_open       BOOLEAN         NOT NULL DEFAULT FALSE,
    ingested_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

SELECT create_hypertable(
    'silver.telemetry_raw', 'event_ts',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);

CREATE INDEX IF NOT EXISTS ix_telemetry_fridge_time
    ON silver.telemetry_raw (fridge_id, event_ts DESC);

-- --- Hypertable des alertes -----------------------------------------------
CREATE TABLE IF NOT EXISTS silver.alerts (
    alert_id        TEXT            NOT NULL,
    opened_at       TIMESTAMPTZ     NOT NULL,
    closed_at       TIMESTAMPTZ,
    site_id         TEXT            NOT NULL,
    fridge_id       TEXT            NOT NULL,
    severity        TEXT            NOT NULL
        CHECK (severity IN ('INFO', 'WARN', 'BREAKAGE_RISK', 'CRITICAL')),
    peak_temp_c     NUMERIC(5,2),
    duration_sec    INTEGER,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    PRIMARY KEY (alert_id, opened_at)
);

SELECT create_hypertable(
    'silver.alerts', 'opened_at',
    chunk_time_interval => INTERVAL '30 days',
    if_not_exists       => TRUE
);

-- --- Historique de dispensation quotidienne -------------------------------
-- Source d'entraînement du modèle Prophet (ml/features.py). Une ligne par
-- (site, médicament, jour). Alimentée par scripts/seed_dimensions.py pour la
-- démo ; en production, ce serait l'export quotidien du logiciel de dispensation.
CREATE TABLE IF NOT EXISTS silver.dispensing_daily (
    observed_at     TIMESTAMPTZ     NOT NULL,
    site_id         TEXT            NOT NULL REFERENCES silver.dim_sites(site_id),
    drug_id         TEXT            NOT NULL REFERENCES silver.dim_drugs(drug_id),
    dispensed_doses INTEGER         NOT NULL CHECK (dispensed_doses >= 0),
    PRIMARY KEY (site_id, drug_id, observed_at)
);

CREATE INDEX IF NOT EXISTS ix_dispensing_site_drug_time
    ON silver.dispensing_daily (site_id, drug_id, observed_at DESC);

-- --- Signaux de rupture + prévisions + recommandations -------------------
CREATE TABLE IF NOT EXISTS silver.shortage_signals (
    signal_ts       TIMESTAMPTZ     NOT NULL,
    source          TEXT            NOT NULL,   -- 'fda' | 'ansm' | 'ema' | … (identifiant de la source)
    drug_id         TEXT            NOT NULL,
    status          TEXT            NOT NULL,
    details         JSONB,
    PRIMARY KEY (drug_id, source, signal_ts)
);

CREATE TABLE IF NOT EXISTS silver.forecasts (
    forecast_ts     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    site_id         TEXT            NOT NULL,
    drug_id         TEXT            NOT NULL,
    horizon_days    INTEGER         NOT NULL,
    predicted_stockout_on DATE,
    shortage_prob   NUMERIC(5,4),
    doses_remaining INTEGER,
    model_version   TEXT,
    PRIMARY KEY (site_id, drug_id, forecast_ts)
);

CREATE TABLE IF NOT EXISTS silver.recommendations (
    rec_id          TEXT            PRIMARY KEY,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    alert_id        TEXT            NOT NULL,
    site_id         TEXT            NOT NULL,
    drug_id         TEXT            NOT NULL,
    brief           JSONB           NOT NULL,
    prompt_hash     TEXT,
    retrieved_chunks TEXT[]
);

-- --- Audit (actions du pharmacien) ---------------------------------------
CREATE TABLE IF NOT EXISTS silver.audit_log (
    audit_id        BIGSERIAL       PRIMARY KEY,
    at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    actor           TEXT            NOT NULL,
    action          TEXT            NOT NULL,
    alert_id        TEXT,
    payload         JSONB
);
