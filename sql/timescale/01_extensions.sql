-- Active l'extension TimescaleDB et quelques helpers.
-- Exécuté automatiquement par l'image postgres via /docker-entrypoint-initdb.d.

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Trois schémas logiques : bronze (brut), silver (typé), gold (marts).
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
