# Architecture

## High-level diagram

```
                                  ┌──────────────────────────────────────┐
                                  │           Public APIs (batch)         │
                                  │  FDA / openFDA / ANSM / OpenPrescr.   │
                                  └────────────┬─────────────────────────┘
                                               │  daily, idempotent
                                               ▼
                                ┌──────────────────────────────┐
                                │    Dagster batch assets      │
                                │  (asset-checked, scheduled)  │
                                └────────────┬─────────────────┘
                                             ▼
       ┌────────────────────────┐    ┌────────────────────────────┐
       │  Cold-chain simulator  │───▶│  Redpanda  (Kafka API)     │
       │  (or real IoT gateway) │    │  topic: coldchain.telemetry│
       └────────────────────────┘    └────────────┬───────────────┘
                                                  │
                                                  ▼
                                ┌────────────────────────────────┐
                                │  Streaming consumer            │
                                │  • parse / validate            │
                                │  • rolling-Z anomaly detect    │
                                │  • emit coldchain.alerts       │
                                └────────────┬───────────────────┘
                                             ▼
                                ┌────────────────────────────────┐
                                │  TimescaleDB (Postgres ext.)   │
                                │  • hypertable: telemetry_raw   │
                                │  • hypertable: alerts          │
                                │  • cont. agg: telemetry_5m     │
                                │  • table: inventory_lots       │
                                │  • table: shortage_signals     │
                                │  • table: forecasts            │
                                └────────────┬───────────────────┘
                                             ▼
                ┌──────────────────────┬──────────────────────┬─────────────────────────┐
                ▼                      ▼                      ▼                         ▼
        ┌──────────────┐    ┌───────────────────┐   ┌────────────────────┐   ┌────────────────────┐
        │ Prophet      │    │   Grafana         │   │ Streamlit          │   │ Ollama RAG          │
        │ shortage     │    │ • IoT real-time   │   │ • alerts feed      │   │ chunks ← protocols/ │
        │ forecast     │    │ • alert rules     │   │ • forecast view    │   │ embed ← bge-small   │
        │ (Dagster)    │    │                   │   │ • SBAR brief   ────┼──▶│ vec ← ChromaDB      │
        └──────────────┘    └───────────────────┘   └────────────────────┘   │ gen ← phi3:mini     │
                                                                              └────────────────────┘
```

## Why a lambda-shaped architecture

We deliberately keep two ingestion paths:

1. **Streaming path** for the IoT telemetry: sub-minute end-to-end
   latency is the whole point of cold-chain monitoring.
2. **Batch path** for the public data sources - FDA / ANSM update at
   most daily, often weekly. Calling them every minute would burn rate
   limits with no benefit.

Both paths land in the **same TimescaleDB**, so the consumer of the data
(Prophet, Streamlit, Grafana) doesn’t have to know how a row got there.
This is the lambda pattern done responsibly: shared sink, divergent
ingestion.

## Why TimescaleDB rather than InfluxDB / Prometheus

- **It’s Postgres.** All Postgres clients, ORMs, BI tools and dbt
  adapters work out of the box. Our consumers (Streamlit + Grafana +
  Prophet) all speak SQL.
- **Hypertables + continuous aggregates** give us the time-series perf
  (chunked storage, time-bucketed materialised views) without giving up
  joins to relational dimensions (inventory, sites, drugs).
- **It scales well enough** for portfolio + small-hospital scale; for a
  national rollout we’d add Citus or migrate to Snowflake: same SQL.

## Why Dagster rather than Airflow

- **Software-defined assets** are the right abstraction here: every
  table downstream of the pipeline is declared as a Python object whose
  freshness, partitioning and dependencies are auditable in one UI.
- **Asset checks** are first-class and let us bind data-quality
  expectations to the asset they validate, rather than to a separate DAG.
- **Local dev is one process** (`dagster dev`), no separate scheduler
  + worker + webserver: friendlier for portfolio reviewers cloning the
  repo.

## Why Ollama + ChromaDB rather than OpenAI + Pinecone

The whole healthcare argument depends on **patient-adjacent data never
leaving the perimeter**. Local LLM (Ollama) + local vector store
(ChromaDB) gives us the demo loop without any external API call. The
prompt template, retriever and citation logic are identical to a managed
implementation; swapping to Bedrock/OpenAI is a 10-line change in
`llm/rag/client.py`.

## Cloud mapping

| Component | OSS used | AWS managed | GCP managed | Azure managed |
| --- | --- | --- | --- | --- |
| Streaming | Redpanda | MSK / Kinesis | Pub/Sub | Event Hubs |
| Time-series | TimescaleDB | RDS Postgres + TimescaleDB | AlloyDB / Bigtable | Azure DB for Postgres |
| Object storage | MinIO | S3 | GCS | Blob |
| Orchestration | Dagster OSS | MWAA | Cloud Composer | Data Factory |
| Forecasting | Prophet | SageMaker Forecast | Vertex AI Forecast | Azure ML |
| Vector store | ChromaDB | OpenSearch / pgvector | Vertex AI Matching Engine | AI Search |
| Embeddings | bge-small-en | Bedrock Titan Embed | text-embedding-005 | Azure OpenAI |
| LLM | phi3:mini (Ollama) | Bedrock Claude / Llama | Vertex AI Llama | Azure OpenAI |
| Real-time dashboards | Grafana OSS | Managed Grafana | Cloud Monitoring | Managed Grafana |
| App layer | Streamlit | App Runner | Cloud Run | Container Apps |

## Failure modes & their handling

| Failure | What happens | Why we’re OK |
| --- | --- | --- |
| Producer dies mid-publish | Some events lost | Redpanda retention 24 h, donc backfill via simulator replay |
| Consumer dies mid-batch | Last commit position re-read | Offsets committed after the write; alerts upserted on a functional key, so replays never duplicate them |
| TimescaleDB down | Consumer buffers, then halts | Backpressure ; events accumulate in Redpanda log up to retention |
| Ollama down | RAG endpoint returns degraded response | Streamlit shows the alert without the LLM brief; the alert itself never depends on the LLM |
| FDA API rate limited | Backoff via tenacity, partial fetch retried at next schedule | Asset shows `STALE` in Dagster, never silently fails |
