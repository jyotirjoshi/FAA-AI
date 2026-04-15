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

_HF_DEFAULT_MODEL = "Qwen/Qwen2.5-72B-Instruct"
_NV_DEFAULT_MODEL = "meta/llama-4-maverick-17b-128e-instruct"

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

        nvapi_key = settings.nvapi_key or os.getenv("NVAPI_KEY", "")
        nvapi_base_url = settings.nvapi_base_url or os.getenv("NVAPI_BASE_URL", "")
        nvapi_model = settings.nvapi_model or os.getenv("NVAPI_MODEL", "")

        litai_key = settings.litai_api_key or os.getenv("LITAI_API_KEY", "")
        litai_base_url = settings.litai_base_url or os.getenv("LITAI_BASE_URL", "")
        litai_model = settings.litai_model or os.getenv("LITAI_MODEL", "")

        hf_token = (
            settings.hf_api_token
            or os.getenv("HF_API_TOKEN", "")
            or os.getenv("HF_TOKEN", "")
        )
        hf_base_url = settings.hf_api_base_url or os.getenv("HF_API_BASE_URL", "")
        hf_model = settings.hf_model or os.getenv("HF_MODEL", "")

        # Highest precedence: explicit NVAPI key.
        if nvapi_key:
            base_url = nvapi_base_url or "https://integrate.api.nvidia.com/v1"
            api_key = nvapi_key
            model = nvapi_model or _NV_DEFAULT_MODEL

        # Optional generic LitAI-compatible config (if user routes through OpenAI-compatible base URL).
        elif litai_key:
            if litai_base_url:
                base_url = litai_base_url
            api_key = litai_key
            if litai_model:
                model = litai_model

        # If standard LLM key is not configured but HF token is, use HF Router automatically.
        if (not api_key) and hf_token:
            base_url = hf_base_url or "https://router.huggingface.co/v1"
            api_key = hf_token
            model = hf_model or _HF_DEFAULT_MODEL

        # Tolerate accidental spaces around separators in model ids.
        model = (model or "").replace(" / ", "/").replace(" /", "/").replace("/ ", "/").strip()

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @property
    def _endpoints(self) -> list[str]:
        # Support both bases that already include /v1 and ones that don't.
        if self.base_url.endswith("/v1"):
            return [f"{self.base_url}/chat/completions", f"{self.base_url}/completions"]
        return [
            f"{self.base_url}/chat/completions",
            f"{self.base_url}/v1/chat/completions",
            f"{self.base_url}/completions",
            f"{self.base_url}/v1/completions",
        ]

    def _extract_text(self, data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM response did not include choices.")

        first = choices[0] or {}
        message = first.get("message") or {}
        content = message.get("content")

        if isinstance(content, str):
            return content.strip()

        # Some providers return an array of content parts.
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    text_parts.append(str(item["text"]))
            joined = "\n".join(text_parts).strip()
            if joined:
                return joined

        # Legacy completion-style fallback.
        text = first.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

        raise RuntimeError("LLM response did not include textual content.")

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

        last_error: Exception | None = None

        for url in self._endpoints:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code >= 400:
                    resp = await client.post(url, json=alt_payload, headers=headers)
                resp.raise_for_status()
                return self._extract_text(resp.json())
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        raise RuntimeError(f"All LLM endpoints failed for base URL '{self.base_url}'.") from last_error

    async def chat_async(self, user_prompt: str) -> str:
        if not self.api_key:
            return (
                "LLM is not configured. Set one of: "
                "NVAPI_KEY, AI_GAMMA4_KEY, LLM_API_KEY, LITAI_API_KEY, or HF_TOKEN/HF_API_TOKEN."
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        async with httpx.AsyncClient(timeout=_CALL_TIMEOUT) as client:
            answer = await self._call_async(messages, client)

            # If the model refused or produced an empty response, force a direct retry.
            if _is_refusal(answer) or len(answer.strip()) < 24:
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

        cleaned = _strip_intro(answer)
        return cleaned if cleaned else "I could not generate a usable answer for this query."

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
