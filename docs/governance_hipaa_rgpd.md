# Governance - HIPAA, GDPR, and the clinical disclaimer

## Scope of the disclaimer

> **Suivi IoT & Prévention des ruptures de médicaments is portfolio / research code.** It is not a
> medical device, not a clinical decision support system, and must
> never be used to make clinical decisions about real patients. The
> clinical substitution briefs produced by the LLM are demonstrative.
> Any production deployment in a clinical setting would require
> regulatory clearance (FDA 510(k) / MDR class IIa-IIb in the EU),
> clinical validation, ISO 13485, ISO 14971, ISO 62304 and more.

That said, the *patterns* in this repo are designed to be compatible
with the governance regimes healthcare actually needs.

## Data sensitivity classification

| Data class | Example | In scope here? | How we handle it |
| --- | --- | --- | --- |
| **PHI** (patient health information, HIPAA) | Name + diagnosis + drug | **No** | We never ingest patient-level data. |
| **PII** (personally identifiable, GDPR) | Employee email, phone | **No** | Same. |
| **Sensitive personal** (GDPR Art. 9: health, biometric) | Hospitalisation record | **No** | Same. |
| **Non-identifying clinical** | Drug name, ATC code, FDA monograph | **Yes** | Public domain or public regulator data. |
| **Aggregate operational** | Site × drug × day dispensing | **Yes, synthetic** | Generated server-side with fake site names. |
| **Device telemetry** | Fridge temperature, humidity | **Yes, synthetic** | Simulated; mapped to fictional fridge IDs. |

**Rule of thumb**: no field in this project can be linked back to a
real human. A reviewer can verify it by grepping the codebase for
anything resembling a patient identifier: there are none.

## HIPAA compatibility patterns we adopt anyway

Even though we don’t touch PHI, we use the patterns a hospital would
demand of us:

- **Encryption in transit** between every service (TLS-capable
  configs; the demo runs over Docker internal network without TLS for
  simplicity, but every config flag is documented).
- **Encryption at rest**: TimescaleDB and MinIO volumes would be
  mounted on an encrypted FS in production (documented in
  `docs/architecture.md` deployment notes).
- **No PHI in logs.** Alert payloads contain drug + site + lot,
  never patient ids: there is nothing personal to redact by design.
- **Audit trail**: every pharmacist action (ack / dismiss) writes an
  `audit_log` row with user, timestamp, alert id, and before/after
  state. The LLM brief persists the prompt hash and retrieved chunk
  ids for reproducibility.
- **LLM in the perimeter**: Ollama + ChromaDB run on the same Docker
  network. No patient-adjacent prompt ever leaves the host. The
  `llm/rag/client.py` implementation makes the API endpoint
  configurable but defaults to `http://ollama:11434`.

## GDPR compatibility patterns

- **Legal basis**: since we use zero personal data, no legal basis
  under Art. 6 is required. A real deployment would be *public
  interest in health* (Art. 9(2)(i)) for shortage mitigation.
- **Right to erasure** is irrelevant here (no personal data). A real
  deployment ingesting patient data would need a deletion routine
  covering every table keyed by `patient_id`, plus tombstone records.
- **Data minimisation**: we aggregate dispensing at (site, drug, day)
  granularity, never patient × day.
- **Retention**: the telemetry hypertable has a 90-day retention
  policy; alerts and the audit log have none (audit-grade conservation).
- **Regional isolation**: every component runs on-prem or in an
  EU-sovereign cloud in production. Nothing in this repo depends on
  cross-border services.

## Model governance (for the LLM)

- **Versioning**: the Ollama model tag (`phi3:mini`) is pinned in
  `.env.example` and printed at the top of every generated brief.
- **Prompt versioning**: prompt templates live in
  `llm/rag/prompts/` (versioned filenames); the brief persists the
  prompt hash used.
- **No autonomous action**: the LLM never writes to inventory or
  triggers redistribution. A pharmacist has to click through.
- **Hallucination mitigation**: the JSON schema + grounding check
  (every citation must resolve to a retrieved chunk) is enforced in
  `llm/rag/validator.py`; an invalid brief is degraded to an
  “insufficient context” card with explicit warnings.

## What would be needed for a real-world deployment

(Out of scope for this repo, but documented to show we know.)

1. **DPO review** and a DPIA if any personal data were to be added.
2. **Regulatory assessment**: medical device classification (EU MDR
   Rule 11 or FDA software-as-a-medical-device framework).
3. **ISO 13485 quality system** for the organisation.
4. **Clinical validation study** with a clinician-in-the-loop panel.
5. **SOC2 Type II / HDS (Hébergeur de Données de Santé)** certification
   of the hosting provider.
6. **Incident reporting channel** to the competent authority.

This list answers the question *“would this be
production-ready for a hospital?”*: the engineering patterns are; the
regulatory envelope is out of portfolio scope.
