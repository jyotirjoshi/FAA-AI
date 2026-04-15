---
title: FAA AI
emoji: ✈
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# FAA + TC Regulation Chatbot (Evidence-Grounded)

This project builds a regulation chatbot that answers from:

- FAA FAR Part 25 pages
- FAA Advisory Circular pages
- Transport Canada CAR 525 pages

The system is retrieval-augmented generation (RAG) with strict citation output and abstention when evidence is weak.

## What this gives you

- Section-aware crawler and parser for nested regulations
- Chunking + local vector index using sentence-transformers
- FastAPI `/chat` endpoint with citations and confidence
- Web chat UI
- Website-first ingestion for the three target sources
- Optional PDF ingestion when needed for internal material

## Important accuracy note

No LLM system can guarantee literal 100% correctness in all cases. This implementation is designed to maximize reliability by:

- Using retrieved context as the primary source, supplemented by regulatory knowledge
- Always returning a complete, detailed answer — never refusing to answer
- Returning explicit source citations for every claim backed by retrieved context
- Using deterministic generation (`temperature=0`)

## Setup

1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` from `.env.example` and set either naming style:

- `AI_GAMMA4_KEY`, `AI_GAMMA4_BASE_URL`, `AI_GAMMA4_MODEL`
- or `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`
- or Hugging Face Router: `HF_TOKEN` (or `HF_API_TOKEN`), optional `HF_MODEL`, optional `HF_API_BASE_URL`
- or NVIDIA API: `NVAPI_KEY`, optional `NVAPI_MODEL`, optional `NVAPI_BASE_URL`
- or LitAI-compatible route: `LITAI_API_KEY`, optional `LITAI_MODEL`, optional `LITAI_BASE_URL`
- or Anthropic API: `ANTHROPIC_API_KEY`, optional `ANTHROPIC_MODEL`, optional `ANTHROPIC_BASE_URL`

Example for Hugging Face Router:

```bash
HF_TOKEN=hf_xxx
HF_MODEL=Qwen/Qwen2.5-72B-Instruct
HF_API_BASE_URL=https://router.huggingface.co/v1
```

If `LLM_API_KEY`/`AI_GAMMA4_KEY` is not set, the app automatically falls back to Hugging Face when `HF_TOKEN` is present.

NVIDIA example:

```bash
NVAPI_KEY=nvapi_xxx
NVAPI_MODEL=meta/llama-4-maverick-17b-128e-instruct
NVAPI_BASE_URL=https://integrate.api.nvidia.com/v1
```

Provider precedence in runtime:
1. `NVAPI_KEY`
2. `ANTHROPIC_API_KEY`
3. `HF_TOKEN` / `HF_API_TOKEN`
4. `LITAI_API_KEY`
5. `AI_GAMMA4_KEY` / `LLM_API_KEY`

## Build the index

### Crawl websites

```bash
python scripts/build_index.py
```

This command crawls the three configured regulation websites and builds the local vector index.
If FAA DRS access is blocked (403), the pipeline also uses an eCFR Part 25 fallback source to preserve Part 25 coverage.

For a clean website-only rebuild (recommended):

```bash
python scripts/build_index.py --reset --website-only
```

For full Title 14 CFR coverage by Parts and Sections (eCFR API):

```bash
python scripts/build_index.py --reset --website-only --title14-full
```

To ingest only the three requested websites (FAA DRS Part 25, FAA Advisory Circulars, TC CAR 525) plus Title 14 by Part and Section:

```bash
python scripts/build_index.py --reset --website-only --title14-full --title14-history-limit 1 --source faa_far_part25 --source faa_advisory_circulars --source tc_car_525
```

To include historical snapshots (recommended for legal change tracking):

```bash
python scripts/build_index.py --reset --website-only --title14-full --title14-history-limit 3
```

`--title14-history-limit` controls how many issue dates are ingested.
Use larger values for deeper historical analysis.
Set `--title14-history-limit 0` to ingest all available historical snapshots.

This mode ingests the current Title 14 snapshot plus a previous snapshot by default, so the chatbot can answer change-aware questions.

For a bounded test run first:

```bash
python scripts/build_index.py --reset --website-only --title14-full --title14-max-parts 20
```

If you want current only, use `--title14-history-limit 1`.

### Add PDFs (optional)

```bash
python scripts/build_index.py --skip-crawl --pdf path/to/doc1.pdf --pdf path/to/doc2.pdf
```

### Add all PDFs from folders (optional)

```bash
python scripts/build_index.py --skip-crawl --pdf-dir "OneDrive_2026-03-20" --pdf-dir "fwdnosubject (1)"
```

## Run API + UI

```bash
uvicorn src.api.main:app --reload
```

Then open:

- http://127.0.0.1:8000

## API usage

`POST /chat`

```json
{
  "question": "What are the icing requirements for transport category airplanes?"
}
```

Response shape:

```json
{
  "answer": "... [C1] ...",
  "citations": [
    {
      "id": "C1",
      "title": "...",
      "section_path": "...",
      "url": "...",
      "source": "faa_far_part25",
      "score": 0.82
    }
  ],
  "confidence": 0.82,
  "grounded": true
}
```

### Compliance plan endpoint (renovation workflow)

`POST /compliance-plan`

```json
{
  "renovation_request": "Install new lavatory door layout and change communication unit.",
  "tcds_text": "TCDS excerpt here including model and certification basis...",
  "governing_body_hint": "FAA"
}
```

The response includes a structured draft compliance plan with citations, plus explicit effective-date checks.

For historical questions, ask with a date phrase such as `as of 2019` or `as of 2024-01-01`.
The retriever prioritizes chunks whose `issue_date` best matches the requested date.

## Hardening for production

- Add reranking (cross-encoder) before final context assembly.
- Add citation verifier that checks each claim against snippet spans.
- Version document snapshots and keep immutable index versions.
- Add regression test set of known regulation Q/A pairs.
- Add human review workflow for high-risk questions.

## Notes on crawlers

This starter uses `httpx + BeautifulSoup` for speed and simplicity.
If needed, you can replace crawling with `scrapy` or `crawlee` for larger scale and better scheduling.
