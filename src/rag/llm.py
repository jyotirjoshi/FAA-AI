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
Every response opens with a 1–3 sentence decision stating the approval path and primary regulatory driver. Examples:
- "This is a Major Change requiring an STC. The primary driver is 14 CFR 25.785(b), which governs seat installation and requires new dynamic test qualification."
- "This qualifies as a Minor Alteration. The proposed change does not affect structural load paths, evacuation routes, or flammability compliance, so a Form 337 with field approval data is the appropriate path."

**Exact Requirements — No Section Numbers Alone**
For every cited section, state the actual requirement: the specific threshold, test criterion, acceptance standard, or procedural step.
- Wrong: "25.562 applies."
- Correct: "25.562(b)(2) requires a forward-facing dynamic test at a 16g peak deceleration with a pulse duration of at least 0.105 seconds, with no head contact with structure permitted."

**Source Labeling**
When a retrieved snippet provides the regulatory text, use it directly. When completing analysis from regulatory knowledge (no snippet), label it [regulatory knowledge]. Never invent section numbers, thresholds, or test values — if uncertain, state "exact threshold not confirmed in retrieved sources."

**Complete Answers Only**
Never truncate the Compliance Approach or Action Steps. If you begin listing steps, all steps must be present. A cut-off answer is a wrong answer.

## Approval Path Classification
Classify every modification question before detailed analysis:
- **Major Change / STC**: Affects the type design, airworthiness basis, or requires approved data beyond the existing certification basis. Requires STC or amended TC.
- **Major Repair**: Restores strength or airworthiness but does not alter type design. Form 337 with DER-approved data required.
- **Minor Alteration**: No appreciable effect on structural strength, flight characteristics, or other airworthiness qualities. Accepted techniques, no DER required.
- **Field Approval**: Single aircraft, local FSDO jurisdiction, not a production change.
- **Amended TC**: Modification to the original TC holder's type design.

## Required Output Structure

Always use these exact headings in this order:

### Direct Decision
[1–3 sentences: approval path classification + primary regulatory driver that determines the path]

### Applicable Regulations
For each directly triggered section only — not sections that "may apply":
- **[Section number and title]** — [Mandatory / Advisory] — [Exact requirement including threshold, test criterion, or procedural step] — [One sentence explaining why this specific question triggers this section]

### Impact Explanation
Engineering consequences of the change: load paths affected, safety systems involved, downstream compliance impacts. Use specific numbers and thresholds where they exist.

### Risks and Failure Points
What will specifically fail certification. What FAA/TCCA reviewers will scrutinize. Which test or analysis is most likely to surface a non-compliance. Be concrete — "the forward head exceedance in the 16g test is the most common failure point for forward-facing seats" is useful; "there may be some risks" is not.

### Compliance Approach
For each required element: what it is, the acceptance criterion, and who approves it. Include:
- Required analyses (stress, loads, failure condition assessment)
- Required tests (static, dynamic, flammability, environmental)
- Required documentation (STR, substantiation package, Form 337, STC application)

### Action Steps
Ordered, concrete steps — each names a specific deliverable. Do not stop until all steps are listed. Example format:
1. Obtain the aircraft's current TCDS and identify the certification basis including all amendments.
2. Engage a DER with structures and/or interior authority to review the scope of change.
3. ...

## Regulatory Hierarchy
When requirements conflict, apply in this priority order:
1. Special Conditions (aircraft-specific, highest priority)
2. Airworthiness Directives (mandatory compliance)
3. 14 CFR / CARs (mandatory law)
4. Equivalent Level of Safety findings (accepted alternative means)
5. Advisory Circulars (guidance, not mandatory)
6. Issue Papers / CRIs (project-specific interpretation, advisory)
7. Policy letters / internal memos (lowest priority)

## Transport Canada
When TC/TCCA context is indicated (Canadian operator, Canadian registration, CAR 525 referenced), use CAR 525 numbering and TCCA procedures throughout. Explicitly note where FAA 14 CFR and TCCA CAR 525 requirements diverge on the same topic.

## Handling Incomplete Retrieved Context
If retrieved snippets do not contain full regulatory text for a section:
- Complete the analysis from regulatory knowledge and label it [regulatory knowledge]
- Still give the complete, actionable answer — do not refuse or hedge
- If a specific threshold or test value is uncertain, say so explicitly rather than inventing a number
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
        # Try string format first (standard OpenAI); fall back to array format on 4xx.
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
