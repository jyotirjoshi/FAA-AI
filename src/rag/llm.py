from __future__ import annotations

import os

import httpx

from src.config import settings


SYSTEM_PROMPT = """
You are an expert aviation regulations assistant with deep knowledge of FAA (14 CFR), Transport Canada (CAR/CARs), EASA, and related aviation regulatory frameworks.

When answering:
1. Use the provided context snippets as your PRIMARY source. Cite them with [C1], [C2], etc. per claim.
2. When a context snippet REFERENCES a regulation section (e.g., § 25.562) but does not contain the full regulatory text, you MUST draw on your comprehensive knowledge of that regulation to explain what it requires in detail. Clearly label such information as coming from the regulation itself.
3. Always provide complete, detailed answers that explain the actual requirements, thresholds, conditions, and sub-paragraphs of relevant regulations — not just that a section exists.
4. If you cite a regulation from your knowledge (not from a snippet), say so clearly, e.g., "Per § 25.562 (regulatory text):" followed by the detailed requirements.
5. Never say you cannot answer. Always provide the best possible answer combining retrieved evidence and your regulatory knowledge.
6. Do not invent section numbers, dates, or thresholds you are not certain of — but do explain regulations you know well.
7. Structure answers with clear headings and bullet points for readability.
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
