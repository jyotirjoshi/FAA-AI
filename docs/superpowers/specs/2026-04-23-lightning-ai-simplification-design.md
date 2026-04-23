# Design Spec: Lightning.ai Single-Provider Simplification
**Date:** 2026-04-23
**Status:** Approved

## Problem

The current LLM client has multi-provider fallback logic that contains a bug: when `HF_TOKEN` is present (always true on HuggingFace Spaces), the code actively redirects Lightning.ai URLs to HuggingFace Router, meaning the configured Lightning.ai key is never actually used. This causes responses from a weaker model, producing irrelevant law citations, truncated answers (max_tokens=1200), and wrong explanations.

## Goal

Make the system reliably use `openai/gpt-5.4-2026-03-05` on Lightning.ai with correct token limits and a sharpened system prompt that eliminates irrelevant law citations and forces complete, accurate answers.

## Approach: Full Simplification (Single Provider)

Remove all multi-provider complexity. One clean OpenAI-compatible client. No fallbacks, no override logic, no provider candidate lists.

## Architecture

### LLM Client (`src/rag/llm.py`)

**Provider:** Lightning.ai OpenAI-compatible API
- Base URL: `https://lightning.ai/api/v1`
- Endpoint: `POST /chat/completions`
- Auth: `Authorization: Bearer <LLM_API_KEY>`
- Model: `openai/gpt-5.4-2026-03-05`
- `max_tokens`: 4096 (up from 1200)
- `temperature`: 0.0
- Timeout: 55s (up from 25s)

**Request format:** Try string content first, fall back to array format on 4xx:
```json
{ "model": "...", "messages": [...], "max_tokens": 4096, "temperature": 0.0 }
```
Array format fallback (Lightning.ai also accepts):
```json
"content": [{ "type": "text", "text": "..." }]
```

**Retry logic:** On refusal or response < 24 chars, send one retry that includes the original context + a directive to answer directly. No cross-provider fallback.

**Error handling:** On final failure, return a clear error string. Never silently fall back to a weaker model.

**Removed entirely:**
- `_build_provider_candidates()`
- `_provider_candidates` list
- All `nvapi_*`, `hf_*`, `anthropic_*`, `litai_*`, `ai_gamma4_*` provider branches
- Lightning.ai redirect logic (`"lightning.ai" in base_url.lower()` blocks)

### Configuration (`src/config.py`)

Simplified settings — only the fields needed for a single OpenAI-compatible provider:

| Field | Default | Source |
|-------|---------|--------|
| `llm_base_url` | `https://lightning.ai/api/v1` | env `LLM_BASE_URL` |
| `llm_api_key` | `""` | env `LLM_API_KEY` |
| `llm_model` | `openai/gpt-5.4-2026-03-05` | env `LLM_MODEL` |
| `embedding_model` | `sentence-transformers/all-MiniLM-L6-v2` | unchanged |
| `top_k` | `10` | unchanged |
| `min_relevance` | `0.12` | unchanged |

All other provider-specific fields removed.

### HuggingFace Space Secrets

Set in HF Space → Settings → Variables and secrets:
- `LLM_API_KEY` = `aaf26c7c-c3c1-405a-babb-7783f49f1138`
- `LLM_BASE_URL` = `https://lightning.ai/api/v1`
- `LLM_MODEL` = `openai/gpt-5.4-2026-03-05`

### Local `.env`

Same values as above for local development. File is in `.gitignore` and never committed.

## System Prompt Changes

### Root Cause of Irrelevant Laws

Current prompt says "build a regulation map before answering" with no relevance gate — the model lists every section it associates with the topic rather than only what the question directly triggers.

### New Prompt Rules

1. **Relevance gate**: Only cite a regulation if the question directly and specifically triggers it. A section that "may relate" is not cited.
2. **Decision first**: Every response opens with a 1–3 sentence decision: approval path classification + primary regulatory driver. No preamble.
3. **Exact requirements for every cited section**: State the actual threshold, test criterion, or procedural requirement — not just the section name or number.
4. **Source labeling**: `[retrieved source]` vs `[regulatory knowledge]` when snippet text is unavailable.
5. **No truncation**: Compliance Approach and Action Steps must always be complete.
6. **Fixed output structure**: Direct Decision → Applicable Regulations → Impact Explanation → Risks & Failure Points → Compliance Approach → Action Steps.

## Files Changed

| File | Change |
|------|--------|
| `src/rag/llm.py` | Full rewrite of `LLMClient` — single provider, new system prompt |
| `src/config.py` | Remove all multi-provider fields, set Lightning.ai defaults |
| `.env` | Create with Lightning.ai credentials (local dev only) |

## Success Criteria

- Responses cite only regulations directly triggered by the question
- Responses are complete — no cut-off at Action Steps
- Correct approval path classification (Major/Minor/STC/Field Approval)
- Exact regulation thresholds stated (e.g. "16g forward dynamic test per 25.562(b)(2)")
- No Lightning.ai key override by HF_TOKEN logic
