from __future__ import annotations

import asyncio
import os
import re

import httpx

from src.config import settings


SYSTEM_PROMPT = """
You are a senior aviation certification engineer and Designated Engineering Representative (DER) with deep expertise in FAA 14 CFR, Transport Canada CARs, STC processes, and Part 25 transport category aircraft certification.

Your answers are used directly to complete FAA Form 337, STC applications (FAA Form 8110-12), DER substantiation packages, and conformity records (FAA Form 8100-9). Every answer must be precise, complete, and actionable.

## Decision Rule — No Hedging

Give a definitive classification. Never use "likely," "possibly," "may be," or "probably."

- **Major Change (STC required)**: Change not covered by existing approved data for this aircraft, requires new structural analysis or dynamic testing, or introduces components from a different aircraft model with no approved installation data.
- **Major Repair (Form 337 + DER data)**: Restores airworthiness without altering the type design.
- **Minor Alteration**: Covered by existing approved maintenance data; no new analysis or testing required.

Seat replacement from a different aircraft model is always a Major Change — no exceptions.

## Relevance Gate

Only cite regulations directly triggered by the specific change. Do not list sections that are topically related but not activated. Do not cite Part 382 or Part 121 sections for business jet or Part 91 operations.

## Output Structure

### Direct Decision
Definitive classification + primary regulatory driver + which FAA forms are required.

### Applicable Regulations
Only directly triggered sections:
**[Section]** — [Mandatory/Advisory] — [Exact requirement with thresholds and test criteria] — [Why this specific change triggers it]

### Impact Explanation
Engineering consequences with specific numbers, load values, and test criteria.

### Risks and Failure Points
The specific test or analysis most likely to fail, and why.

### Compliance Approach
Each deliverable: what it is, acceptance criterion, who approves it.

### Action Steps
Numbered, complete list. Include: obtain TCDS, engage DER with appropriate authority, verify TSO authorizations, obtain/conduct required testing, prepare substantiation package, submit to FAA.

### Forms and Documentation Required
Every form needed with specific data blocks to complete.
""".strip()


_REFUSAL_PATTERNS = [
    r"cannot answer with sufficient certainty",
    r"cannot answer.*indexed sources",
    r"insufficient.*indexed sources",
    r"provided context snippets do not contain",
    r"I cannot provide",
    r"unable to answer",
    r"not able to answer",
]

_CALL_TIMEOUT = 90


def _is_refusal(text: str) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in _REFUSAL_PATTERNS)


class LLMClient:
    def __init__(self) -> None:
        self.api_key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = settings.anthropic_model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    async def _post_async(self, messages: list[dict], client: httpx.AsyncClient) -> str:
        # Extract system message and user/assistant turns for Anthropic format
        system_text = "\n\n".join(
            str(m.get("content", "")) for m in messages if m.get("role") == "system"
        ).strip()
        turns = [m for m in messages if m.get("role") in {"user", "assistant"}]

        anthropic_messages = [
            {
                "role": m["role"],
                "content": [{"type": "text", "text": str(m.get("content", ""))}],
            }
            for m in turns
        ]

        payload: dict = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0.0,
            "messages": anthropic_messages,
        }
        if system_text:
            payload["system"] = system_text

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = [
            item["text"]
            for item in (data.get("content") or [])
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
        ]
        answer = "\n".join(parts).strip()
        if not answer:
            raise RuntimeError("Anthropic response contained no text content.")
        return answer

    def _build_messages(self, user_prompt: str, history: list[dict] | None) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for turn in history or []:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    async def stream_async(self, user_prompt: str, history: list[dict] | None = None):
        """Yields ('text', str) chunks then ('done', None) or ('error', str)."""
        import json as _json

        if not self.api_key:
            yield "error", "LLM not configured. Set ANTHROPIC_API_KEY in HuggingFace Space secrets."
            return

        messages = self._build_messages(user_prompt, history)
        system_text = "\n\n".join(
            str(m.get("content", "")) for m in messages if m.get("role") == "system"
        ).strip()
        turns = [m for m in messages if m.get("role") in {"user", "assistant"}]
        anthropic_messages = [
            {"role": m["role"], "content": [{"type": "text", "text": str(m.get("content", ""))}]}
            for m in turns
        ]
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0.0,
            "stream": True,
            "messages": anthropic_messages,
            "system": system_text,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_CALL_TIMEOUT) as client:
                async with client.stream(
                    "POST", "https://api.anthropic.com/v1/messages",
                    json=payload, headers=headers
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if not raw:
                            continue
                        try:
                            event = _json.loads(raw)
                        except _json.JSONDecodeError:
                            continue
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta" and delta.get("text"):
                                yield "text", delta["text"]
            yield "done", None
        except Exception as exc:  # noqa: BLE001
            yield "error", str(exc)

    async def chat_async(self, user_prompt: str, history: list[dict] | None = None) -> str:
        if not self.api_key:
            return "LLM is not configured. Set ANTHROPIC_API_KEY in your HuggingFace Space secrets."

        messages = self._build_messages(user_prompt, history)

        async with httpx.AsyncClient(timeout=_CALL_TIMEOUT) as client:
            try:
                answer = await self._post_async(messages, client)

                if _is_refusal(answer) or len(answer.strip()) < 24:
                    retry_messages = messages + [
                        {"role": "assistant", "content": answer},
                        {
                            "role": "user",
                            "content": (
                                "Your response did not fully answer the question. "
                                "Apply your full knowledge of 14 CFR, Transport Canada CARs, "
                                "STC processes, and DER substantiation requirements. "
                                "Follow the required structure: Direct Decision, Applicable Regulations, "
                                "Impact Explanation, Risks and Failure Points, Compliance Approach, "
                                "Action Steps, Forms and Documentation Required."
                            ),
                        },
                    ]
                    answer = await self._post_async(retry_messages, client)

                return answer.strip() if answer.strip() else "Could not generate a usable answer."

            except Exception as exc:  # noqa: BLE001
                return f"Request failed. Please try again.\n\n⚠ {exc}"

    def chat(self, user_prompt: str) -> str:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.chat_async(user_prompt))
                return future.result(timeout=95)
        else:
            return asyncio.run(self.chat_async(user_prompt))
