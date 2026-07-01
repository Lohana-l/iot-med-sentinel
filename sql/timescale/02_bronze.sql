-- ---------------------------------------------------------------------------
-- Tables bronze : zone d'atterrissage brute pour les payloads des API publiques.
-- On garde le JSONB indéfiniment ; les vues silver castent ce qui nous intéresse.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS bronze.fda_shortages (
    ingested_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source_row_id    TEXT            PRIMARY KEY,
    payload          JSONB           NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.openfda_labels (
    ingested_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source_row_id    TEXT            PRIMARY KEY,   -- set_id issu d'openFDA
    payload          JSONB           NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.ansm_signalements (
    ingested_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source_row_id    TEXT            PRIMARY KEY,
    payload          JSONB           NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.openprescribing_usage (
    ingested_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source_row_id    TEXT            PRIMARY KEY,   -- practice||bnf_code||month (clé composite)
    payload          JSONB           NOT NULL
);
