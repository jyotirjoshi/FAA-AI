from __future__ import annotations

import asyncio
import os
import re

import httpx

from src.config import settings


SYSTEM_PROMPT = """
You are an expert aviation regulations assistant with deep knowledge of FAA (14 CFR), Transport Canada (CAR/CARs), EASA, and related aviation regulatory frameworks.

CRITICAL RULES — these override everything else:
- NEVER introduce yourself or mention your name, model, or that you are an AI.
- NEVER say "I cannot answer", "I cannot provide", "insufficient certainty", "indexed sources", or any similar refusal. These phrases are strictly forbidden.
- ALWAYS answer the question directly and completely, no matter what.
- If the context snippets don't contain the full regulation text, use your own regulatory knowledge and state "(from regulation knowledge)".

When answering:
1. Use the provided context snippets as your PRIMARY source. Cite them with [C1], [C2], etc. per claim.
2. When a snippet only references a section number, explain that section's full requirements from your knowledge.
3. Always include the actual requirements, thresholds, conditions, and sub-paragraphs — not just that a section exists.
4. Structure answers with clear markdown headings and bullet points.
5. Do not invent section numbers, dates, or thresholds you are not certain of.
""".strip()

# Phrases that indicate the model refused instead of answering
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

_INTRO_PATTERNS = [
    r"^(As |I am |I'm )(an? )?(AI|language model|assistant|GLM|chatbot)[^.]*\.",
    r"^(Hello|Hi)[!,]?\s+(I('m| am)|my name is)[^.]*\.",
]

# Per-call timeout (seconds). Two calls max = 2 × 25 = 50s, safely under nginx 60s limit.
_CALL_TIMEOUT = 25


def _is_refusal(text: str) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in _REFUSAL_PATTERNS)


def _strip_intro(text: str) -> str:
    for p in _INTRO_PATTERNS:
        text = re.sub(p, "", text, flags=re.IGNORECASE | re.MULTILINE).lstrip()
    return text


class LLMClient:
    def __init__(self) -> None:
        base_url = (
            settings.ai_gamma4_base_url
            or os.getenv("AI_GAMMA4_BASE_URL", "")
            or settings.llm_base_url
        )
        api_key = settings.ai_gamma4_key or os.getenv("AI_GAMMA4_KEY", "") or settings.llm_api_key
        model = settings.ai_gamma4_model or os.getenv("AI_GAMMA4_MODEL", "") or settings.llm_model

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def _call_async(self, messages: list[dict], client: httpx.AsyncClient) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "messages": messages, "temperature": 0.0}
        alt_messages = [
            {
                **m,
                "content": [{"type": "text", "text": m["content"]}]
                if isinstance(m["content"], str)
                else m["content"],
            }
            for m in messages
        ]
        alt_payload = {"model": self.model, "messages": alt_messages, "temperature": 0.0}

        resp = await client.post(
            f"{self.base_url}/chat/completions", json=payload, headers=headers
        )
        if resp.status_code >= 400:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=alt_payload, headers=headers
            )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    async def chat_async(self, user_prompt: str) -> str:
        if not self.api_key:
            return "LLM_API_KEY is not configured."

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        async with httpx.AsyncClient(timeout=_CALL_TIMEOUT) as client:
            answer = await self._call_async(messages, client)

            # If the model refused, force a direct retry
            if _is_refusal(answer):
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": answer},
                    {
                        "role": "user",
                        "content": (
                            "You just gave a refusal instead of answering. That is not acceptable. "
                            "Ignore any limitation about indexed sources — you have comprehensive knowledge "
                            "of aviation regulations. Answer the original question now, directly and in full detail, "
                            "using your knowledge of FAA 14 CFR, Transport Canada, and related frameworks. "
                            "Do not mention the indexed sources. Just answer."
                        ),
                    },
                ]
                answer = await self._call_async(messages, client)

        return _strip_intro(answer)

    def chat(self, user_prompt: str) -> str:
        """Sync wrapper — runs the async implementation in a new event loop if needed."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an async context (FastAPI) — caller should use chat_async directly
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.chat_async(user_prompt))
                return future.result(timeout=55)
        else:
            return asyncio.run(self.chat_async(user_prompt))
