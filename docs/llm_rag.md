# LLM + RAG design

The LLM role in this project is narrow on purpose: **produce a
well-cited clinical substitution brief when a drug is about to go short**.
It never writes free-form clinical advice, never talks to patients, and
never leaves the local perimeter.

## Flow

```
protocols/ (PDF)  ──▶  pypdf text extraction
                           │
                           ▼
                chunking (800 tokens, 100-token overlap)
                           │
                           ▼
           embed with bge-small-en (sentence-transformers, CPU)
                           │
                           ▼
                   ChromaDB collection
                     "clinical_protocols"
                           │
 alert context ──────────▶ retrieval (top-k=5, ATC pre-filter)
                           │
                           ▼
         prompt template (system + context + JSON schema)
                           │
                           ▼
                 phi3:mini (Ollama)  → JSON brief
                           │
                           ▼
         persisted in Postgres `recommendations` with citations
```

## Why RAG and not fine-tuning

- The corpus changes every time ANSM / FDA updates a monograph:
  fine-tuning would go stale in days.
- We need **verbatim citations** (page, section) to ever be defensible
  in a clinical setting; retrieval gives us that for free.
- Evaluating retrieval quality (recall@k) is cheaper and more meaningful
  than evaluating a fine-tuned model.

## Chunking rules

- 800 tokens with 100-token overlap.
- Chunk boundaries prefer headings and table rows, using pypdf’s
  layout-aware extraction.
- Every chunk stores `{document_id, page_from, page_to, section}` as
  metadata so citations can reference the exact location.

## Retrieval

- Chroma similarity search (cosine), top-k=5.
- When the alert context mentions a specific ATC code, we pre-filter
  chunks whose metadata tags include that code: this dramatically
  improves precision. If the filtered query fails, we retry unfiltered.

## Prompt template (abbreviated)

```text
SYSTEM
You are a clinical pharmacy assistant. You write substitution briefs for
on-call pharmacists in English or French depending on the input. You
NEVER invent drug names, doses, or contraindications. Every clinical
claim MUST cite the document and page it came from in the supplied
context. If the context does not contain a claim, say "insufficient
context". Return strict JSON matching the schema.

USER
Alert: breakage_risk on lot {lot_id} of {drug}. Suspect doses: {n}.
Current site: {site}. Forecast: shortage in {days}d, prob {p}.

Context (retrieved from the clinical protocol corpus):
--- begin context ---
{top_k_chunks_with_metadata}
--- end context ---

Return JSON:
{
  "alternatives": [{ "name": str, "atc": str, "posology_note": str,
                     "citations": [ {"doc": str, "page": int } ] }],
  "redistribution_candidates": [ { "site": str, "surplus_doses": int } ],
  "confidence": "high"|"medium"|"low",
  "insufficient_context": bool
}
```

## Why JSON-schema output

Downstream Streamlit code reads the brief to render structured cards
(one per alternative, citations as links). Free-form markdown is a
liability; JSON with Pydantic validation keeps the UI trustworthy.
We use `response_format={"type":"json_object"}` via the Ollama chat API
and validate with Pydantic.

## Evaluation

- **Chunking**: `tests/unit/test_chunker.py` covers ATC extraction and
  chunk boundaries on seed protocols.
- **Grounding**: `tests/unit/test_rag_validator.py` covers the schema
  validation and the citation check: every `citations` entry must
  reference a `(doc, page)` tuple that exists in the retrieved chunks,
  otherwise the brief is degraded with warnings.
- **End to end**: tests under the `llm` pytest marker require a running
  Ollama and are opt-in (skipped in CI).

## Safety rails

- **Insufficient-context path**: if the prompt cannot satisfy the
  `citations` rule, the model is instructed to return
  `insufficient_context: true` and the UI shows *“Not enough protocol
  coverage: please consult the pharmacist reference.”*
- **Audit**: every brief is persisted with its prompt hash and the IDs
  of the retrieved chunks. Reproducible inspection.
- **No patient data**: prompts never include patient identifiers. Alert
  context is site-level + lot-level only.
