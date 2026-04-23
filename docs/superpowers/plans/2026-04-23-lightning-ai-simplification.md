# Lightning.ai Single-Provider Simplification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken multi-provider LLM client with a single clean Lightning.ai client using `openai/gpt-5.4-2026-03-05`, fix token limits and timeout, and sharpen the system prompt to eliminate irrelevant law citations and truncated answers.

**Architecture:** Single OpenAI-compatible `httpx` client pointed at `https://lightning.ai/api/v1/chat/completions`. All multi-provider fallback logic, Lightning.ai URL redirect bugs, and unused provider fields removed. Config simplified to three env vars: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.

**Tech Stack:** Python 3.11+, FastAPI, httpx, pydantic-settings, HuggingFace Spaces (git-based deployment)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/config.py` | Modify | Settings — remove all multi-provider fields |
| `src/rag/llm.py` | Modify | LLMClient + system prompt — single Lightning.ai provider |
| `.env` | Create | Local dev credentials (gitignored) |

No new files created. `src/rag/pipeline.py`, `src/rag/retriever.py`, `src/api/main.py` are untouched.

---

## Task 1: Simplify `src/config.py`

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Replace the full contents of `src/config.py`**

Open `src/config.py` and replace everything with:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_base_url: str = "https://lightning.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "openai/gpt-5.4-2026-03-05"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    top_k: int = 10
    min_relevance: float = 0.12

    max_pages_per_source: int = 1200
    request_timeout_seconds: int = 20

    project_root: Path = Path(__file__).resolve().parents[1]
    raw_dir: Path = project_root / "data" / "raw"
    processed_dir: Path = project_root / "data" / "processed"
    index_dir: Path = project_root / "data" / "index"


settings = Settings()
```

- [ ] **Step 2: Verify import works**

Run from the `FAA_mac/` directory:

```bash
python -c "from src.config import settings; print(settings.llm_base_url, settings.llm_model)"
```

Expected output:
```
https://lightning.ai/api/v1 openai/gpt-5.4-2026-03-05
```

- [ ] **Step 3: Commit**

```bash
git add src/config.py
git commit -m "simplify config: single Lightning.ai provider, remove multi-provider fields"
```

---

## Task 2: Rewrite `src/rag/llm.py`

**Files:**
- Modify: `src/rag/llm.py`

- [ ] **Step 1: Replace the full contents of `src/rag/llm.py`**

Open `src/rag/llm.py` and replace everything with:

```python
from __future__ import annotations

import asyncio
import os
import re

import httpx

from src.config import settings


SYSTEM_PROMPT = """
You are a senior aviation certification engineer operating at DER/ODA/ACO level. Your job is to make certification-quality decisions, identify the exact governing regulations, and give engineers actionable compliance guidance.

## Core Rules

**Relevance Gate — Applied Before Every Response**
Only cite a regulation if the question directly and specifically triggers it. Do not list sections that "may relate" or are "worth considering." If a section is not activated by this specific question, it does not appear in your answer.

**Decision First — No Exceptions**
Every response opens with a 1–3 sentence decision: approval path + primary regulatory driver. Examples:
- "This is a Major Change requiring an STC. The primary driver is 14 CFR 25.785(b), which governs seat installation and requires new dynamic test qualification."
- "This qualifies as a Minor Alteration. The proposed change does not affect structural load paths, evacuation routes, or flammability compliance, so a Form 337 with field approval data is the appropriate path."

**Exact Requirements — No Section Numbers Alone**
For every cited section, state the actual requirement: the specific threshold, test criterion, acceptance standard, or procedural step. "25.562 applies" is not acceptable. "25.562(b)(2) requires a forward-facing dynamic test at a 16g peak deceleration with a pulse duration of at least 0.105 seconds, with no head contact permitted" is correct.

**Source Labeling**
When a retrieved snippet provides the regulatory text, use it directly. When completing analysis from knowledge (no snippet), label it: [regulatory knowledge]. Never invent section numbers, thresholds, or test values you are not certain of — state "exact threshold not confirmed in retrieved sources" instead.

**Complete Answers Only**
Never truncate the Compliance Approach or Action Steps. If you begin listing action steps, all steps must be present. A cut-off answer is a wrong answer.

## Approval Path Classification
Classify every modification question before detailed analysis:
- **Major Change / STC**: Affects the type design, airworthiness basis, or requires approved data beyond existing certification basis
- **Major Repair**: Restores strength or airworthiness but does not alter type design — Form 337 with DER-approved data
- **Minor Alteration**: No appreciable effect on structural strength, flight characteristics, or other airworthiness qualities
- **Field Approval**: Single aircraft, local FSDO jurisdiction, not a production change
- **Amended TC**: Modification to the original TC holder's type design

## Required Output Structure

### Direct Decision
[1–3 sentences: approval path classification + primary regulatory driver]

### Applicable Regulations
[For each triggered section — and only triggered sections:]
- **[Section number]** — [Mandatory / Advisory] — [Exact requirement: threshold, test criterion, or procedural requirement] — [Why this specific question triggers it]

### Impact Explanation
[Engineering consequences: load paths, safety systems, downstream compliance. Quantitative where thresholds exist.]

### Risks and Failure Points
[What specifically will fail certification. What FAA/TCCA reviewers will focus on. Which test or analysis is most likely to surface a problem.]

### Compliance Approach
[Specific analyses, tests, demonstrations, and documents needed. For each: what it is, what the acceptance criterion is, and who approves it.]

### Action Steps
[Ordered, concrete steps. Each step names a deliverable. Do not stop until all steps are listed.]

## Regulatory Hierarchy
When requirements conflict:
1. Special Conditions (aircraft-specific, highest)
2. Airworthiness Directives
3. 14 CFR / CARs (mandatory law)
4. Equivalent Level of Safety findings
5. Advisory Circulars (guidance, not mandatory)
6. Issue Papers / CRIs (project-specific interpretation)
7. Policy letters / memos (lowest)

## Transport Canada
When TC/TCCA context is present, use CAR 525 numbering and TCCA procedures. Explicitly note where FAA and TCCA requirements diverge.
""".strip()

_REFUSAL_PATTERNS = [
    r"cannot answer with sufficient certainty",
    r"cannot answer.*indexed sources",
    r"insufficient.*indexed sources",
    r"provided context snippets do not contain",
    r"context snippets.*do not.*contain",
    r"available.*content.*does not.*address",
    r"I cannot provide",
    r"unable to answer",
    r"not able to answer",
]

# 55 seconds — safely under nginx/proxy 60s hard limit, enough for 4096-token responses
_CALL_TIMEOUT = 55


def _is_refusal(text: str) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in _REFUSAL_PATTERNS)


class LLMClient:
    def __init__(self) -> None:
        self.base_url = (settings.llm_base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self.api_key = settings.llm_api_key or os.getenv("LLM_API_KEY", "")
        self.model = (settings.llm_model or os.getenv("LLM_MODEL", "")).strip()

    async def _post_async(self, messages: list[dict], client: httpx.AsyncClient) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.0,
        }
        # Lightning.ai accepts both string and array content formats.
        # Try string format first (standard); fall back to array format on 4xx.
        alt_messages = [
            {
                **m,
                "content": [{"type": "text", "text": m["content"]}]
                if isinstance(m["content"], str)
                else m["content"],
            }
            for m in messages
        ]
        alt_payload = {**payload, "messages": alt_messages}

        url = f"{self.base_url}/chat/completions"
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            resp = await client.post(url, json=alt_payload, headers=headers)
        resp.raise_for_status()
        return self._extract_text(resp.json())

    @staticmethod
    def _extract_text(data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM response did not include choices.")
        first = choices[0] or {}
        message = first.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                item["text"]
                for item in content
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
            ]
            joined = "\n".join(parts).strip()
            if joined:
                return joined
        text = first.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        raise RuntimeError("LLM response did not include textual content.")

    async def chat_async(self, user_prompt: str, history: list[dict] | None = None) -> str:
        if not self.api_key:
            return "LLM is not configured. Set LLM_API_KEY in your environment or .env file."

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for turn in history or []:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_prompt})

        async with httpx.AsyncClient(timeout=_CALL_TIMEOUT) as client:
            try:
                answer = await self._post_async(messages, client)

                if _is_refusal(answer) or len(answer.strip()) < 24:
                    retry_messages = messages + [
                        {"role": "assistant", "content": answer},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response did not answer the question. "
                                "Use the regulatory context provided and your knowledge of 14 CFR, "
                                "Transport Canada CARs, and related airworthiness frameworks to answer "
                                "the original question completely. Follow the required output structure: "
                                "Direct Decision, Applicable Regulations, Impact Explanation, "
                                "Risks and Failure Points, Compliance Approach, Action Steps."
                            ),
                        },
                    ]
                    answer = await self._post_async(retry_messages, client)

                return answer.strip() if answer.strip() else "I could not generate a usable answer for this query."

            except Exception as exc:  # noqa: BLE001
                return f"The model request failed. Please try again.\n\n⚠ {exc}"

    def chat(self, user_prompt: str) -> str:
        """Sync wrapper — runs the async implementation in a new event loop if needed."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.chat_async(user_prompt))
                return future.result(timeout=60)
        else:
            return asyncio.run(self.chat_async(user_prompt))
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
python -c "from src.rag.llm import LLMClient, SYSTEM_PROMPT; print('OK — system prompt length:', len(SYSTEM_PROMPT))"
```

Expected output:
```
OK — system prompt length: [any number > 500]
```

- [ ] **Step 3: Commit**

```bash
git add src/rag/llm.py
git commit -m "rewrite LLMClient: single Lightning.ai provider, max_tokens 4096, improved system prompt"
```

---

## Task 3: Create local `.env` file

**Files:**
- Create: `.env` (gitignored — never committed)

- [ ] **Step 1: Create `.env` in the project root (`FAA_mac/`)**

Create the file with these exact contents:

```
LLM_API_KEY=aaf26c7c-c3c1-405a-babb-7783f49f1138
LLM_BASE_URL=https://lightning.ai/api/v1
LLM_MODEL=openai/gpt-5.4-2026-03-05
```

- [ ] **Step 2: Verify config picks up the values**

```bash
python -c "from src.config import settings; print(settings.llm_api_key[:8], settings.llm_base_url)"
```

Expected output (first 8 chars of key):
```
aaf26c7c https://lightning.ai/api/v1
```

- [ ] **Step 3: Confirm `.env` is gitignored**

```bash
git status
```

`.env` must NOT appear in the untracked files list. If it does, check `.gitignore` — the line `.env` must be present.

---

## Task 4: Smoke-test the API locally

**Files:** none changed

- [ ] **Step 1: Start the API server**

```bash
uvicorn src.api.main:app --reload
```

Wait for the line: `Application startup complete.`

- [ ] **Step 2: Send a test question**

In a second terminal:

```bash
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Does replacing a passenger seat cushion require an STC?"}' \
  | python -m json.dumps
```

**Pass criteria:**
1. `answer` field is present and longer than 200 characters
2. `answer` starts with a decision sentence (e.g. "This is a Minor..." or "This qualifies as...")
3. `answer` contains a `### Applicable Regulations` section
4. Response arrives within 60 seconds

If the answer is shorter than 200 chars or does not contain headings, the model call is failing — check the terminal running uvicorn for the error traceback.

- [ ] **Step 3: Test a second question that historically returned irrelevant laws**

```bash
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the flammability requirements for cabin sidewall panels?"}' \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['answer'][:800])"
```

**Pass criteria:**
1. Answer cites 25.853 (flammability) — this is the correct section
2. Answer does NOT cite 25.562 (dynamic seat testing) — that section is irrelevant to sidewall panels
3. Answer contains exact test criteria (e.g. vertical Bunsen burner test, 60-second flame application)

---

## Task 5: Set HuggingFace Space secrets

**Files:** none (HF Space web UI action)

The `.env` file is gitignored and will not be deployed. The HF Space reads secrets from its own environment.

- [ ] **Step 1: Open HuggingFace Space settings**

Go to: `https://huggingface.co/spaces/jyotir1/AirWise/settings`

Log in if prompted.

- [ ] **Step 2: Add three secrets under "Repository secrets"**

Add each one as a secret (not a variable — secrets are encrypted):

| Name | Value |
|------|-------|
| `LLM_API_KEY` | `aaf26c7c-c3c1-405a-babb-7783f49f1138` |
| `LLM_BASE_URL` | `https://lightning.ai/api/v1` |
| `LLM_MODEL` | `openai/gpt-5.4-2026-03-05` |

Click "Add new secret" for each, then save.

---

## Task 6: Push to HuggingFace Space

**Files:** none changed — push existing commits

- [ ] **Step 1: Verify commits are ready**

```bash
git log --oneline -5
```

You should see the two commits from Tasks 1 and 2:
```
<hash> rewrite LLMClient: single Lightning.ai provider, max_tokens 4096, improved system prompt
<hash> simplify config: single Lightning.ai provider, remove multi-provider fields
```

- [ ] **Step 2: Push to the `airwise` remote (jyotir1/AirWise)**

```bash
git push airwise main
```

Expected output ends with:
```
To https://huggingface.co/spaces/jyotir1/AirWise.git
   <old>..<new>  main -> main
```

If you get a rejection (non-fast-forward), pull first:
```bash
git pull airwise main --rebase
git push airwise main
```

- [ ] **Step 3: Wait for the Space to rebuild**

Go to `https://huggingface.co/spaces/jyotir1/AirWise` and watch the build log. The Space rebuilds automatically on push. Wait until status shows **Running** (green).

Typical rebuild time: 2–5 minutes.

- [ ] **Step 4: Live smoke test**

Once the Space is running, open the chat UI and ask:

> "Does replacing a passenger seat cushion require an STC?"

**Pass criteria — same as Task 4 Step 2:**
1. Answer is longer than 200 characters
2. Starts with a decision sentence
3. Contains `### Applicable Regulations` section
4. Arrives within 60 seconds

If the Space returns "LLM is not configured" — the secrets from Task 5 were not saved correctly. Return to HF settings and re-add them, then restart the Space.
