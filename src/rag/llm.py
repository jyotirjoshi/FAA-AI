from __future__ import annotations

import os

import httpx

from src.config import settings


SYSTEM_PROMPT = """
You are an aviation regulations assistant.
You must answer ONLY using the provided context snippets.
If evidence is insufficient or conflicting, say: "I cannot answer with sufficient certainty from the indexed sources."
Always include section-level citations in the answer body like [C1], [C2].
Do not invent regulations, section numbers, dates, or thresholds.
""".strip()


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

    def chat(self, user_prompt: str) -> str:
        if not self.api_key:
            return "LLM_API_KEY is not configured."

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }

        alt_payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": SYSTEM_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_prompt}],
                },
            ],
            "temperature": 0.0,
        }

        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            if resp.status_code >= 400:
                resp = client.post(f"{self.base_url}/chat/completions", json=alt_payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return data["choices"][0]["message"]["content"].strip()
