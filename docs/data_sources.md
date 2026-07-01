# Data sources

A defining goal of this project: **use real public data wherever it
exists**, synthesise the rest with a documented, defensible model.
Nothing is fabricated without a paper trail.

## Reuse rights

Every source is free, unauthenticated and legally reusable (public domain,
CC0 or CC-BY). Anyone can clone the repo and reproduce the same flows,
without an API key or a subscription.

## Summary

| Source | Real / synthetic | Access | Volume (demo) | Refresh |
| --- | --- | --- | --- | --- |
| FDA Drug Shortages | **Real** | `api.fda.gov/drug/shortages.json`: unauthenticated | ~330 active shortages | Daily |
| openFDA Drug Label | **Real** | `api.fda.gov/drug/label.json`: unauthenticated, 240 req/min anonymous | ~20 k active labels | Weekly |
| ANSM (France) | **Real** | Public RSS feed + “ruptures de stock” HTML table | ~5 k signalements | Daily |
| OpenPrescribing.net (UK) | **Real** | REST API, CC-BY licence | 10 k practices × 3 years | Monthly |
| Hospital inventory | **Synthetic** | Seed generator (`scripts/seed_dimensions.py`) | 8 sites × 5 cold-chain drugs, 270 days of dispensing | - |
| Fridge telemetry | **Synthetic** | Our SimPy simulator | 8 × 6 fridges × 30 s | - |
| Clinical substitution protocols | **Synthetic (seed)** + **real (FDA labels)** | Seeded Markdown + downloaded FDA label JSON | ~20 documents | One-off |

## Why synthetic is fine for telemetry

Real hospital fridge telemetry is not public anywhere on earth, and
rightly so: hospitals don’t publish operational data. The simulator’s
distributions are grounded in two documented priors:

- **WHO Technical Specifications for Pharmaceutical Refrigerators
  (WHO/IVB/2014)**: spec’d normal operating range, door-opening
  frequency in clinical settings, typical excursion patterns.
- **WHO PQS E003/RF05** catalogue: compressor failure MTBF figures and
  recovery curves (used as simulator priors, not ingested).

The simulator code (`simulator/model.py`) cites the exact paragraph it
implements. A reviewer auditing our distributions can check them.

## API access patterns

### FDA Drug Shortages
```http
GET https://api.fda.gov/drug/shortages.json?limit=1000
```
- No key required. Rate-limited to 240 req/min anonymous.
- Schema: generic name, status, availability, therapeutic category,
  reason, dates.
- Our extractor paginates via `skip=` offset and deduplicates by
  `(generic_name, status_date)`.

### openFDA Drug Label
```http
GET https://api.fda.gov/drug/label.json?search=openfda.generic_name:"oseltamivir"
```
- Returns full SPL (Structured Product Labeling) JSON including
  indications, contraindications, dosage. We extract the ATC code and
  substitution-relevant fields.
- Used to enrich shortage rows and to build the RAG corpus.

### ANSM
```http
GET https://ansm.sante.fr/actualites.rss
```
- No official API: we parse the public RSS feed of alerts, with a
  respectful User-Agent and aggressive caching.

### OpenPrescribing
```http
GET https://openprescribing.net/api/1.0/spending_by_org/?code=...&format=json
```
- CC-BY licensed GP prescribing data in England. Gives us a realistic
  time-series for demand forecasting when the EU side is quiet.

## Landing schema (bronze vers silver)

Public data lands as-is in `bronze.<source>_<endpoint>` tables with:
- `ingested_at TIMESTAMPTZ`
- `source_row_id TEXT`: for dedup
- `payload JSONB`: full raw record

The silver layer (`sql/timescale/03_silver.sql`) holds the typed tables
used by downstream models. The raw JSONB is kept for audit.

## GDPR / HIPAA treatment

None of the real sources contain PHI or PII: they are drug-level, not
patient-level. The synthetic hospital data uses fake site names and is
aggregated to (site, drug, day), never (patient, drug, day). See
`governance_hipaa_rgpd.md` for the full policy.
