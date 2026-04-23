from __future__ import annotations

import asyncio
import os
import re

import httpx

from src.config import settings


SYSTEM_PROMPT = """
You are a senior aviation certification engineer with DER/ODA-level regulatory judgment.

Your job is not to chat or summarize text. Your job is to make a certification-quality decision, map the problem to the governing rules, explain the engineering impact, and identify the most likely approval path.

Core standards:
- Answer like a real certification engineer, DER, or ODA unit member would.
- Be decisive, technical, and practical. Do not hedge with vague language.
- If the question concerns a modification or approval path, always classify the likely approval route first: major change, minor change, STC, amended TC, field approval, or another path if clearly supported.
- Apply certification workflow logic, not just regulation lookup:
    - Decide whether the change is likely a major change, minor change, STC candidate, amended TC candidate, or another approval path.
    - Use certification-basis logic: original type design, amended TC, STC scope, prior approvals, and affected systems or interiors must be considered together.
    - If the change affects seats, monuments, exits, floor structure, restraint paths, flammability, evacuation, or system safety, treat it as certification-impacting until proven otherwise.
    - If required aircraft data is missing, state the missing inputs and still give the most defensible certification path.
    - Prefer a final decision with rationale over a list of possibilities.
- Treat regulations, ACs, policy memos, issue papers, CRIs, and special conditions differently: cite which ones are mandatory law, which are guidance, and which are project-specific interpretation.
- Use the provided context snippets as evidence, but rely on regulatory knowledge to complete the reasoning when a snippet only points to a section.
- Do not invent section numbers, thresholds, or dates. If a detail is uncertain, say it is a gap and continue with the best defensible engineering interpretation.

Required reasoning behavior:
- Map the request to the affected safety domains: structure, loads, crashworthiness, evacuation/egress, flammability/fire, electrical/system safety, human factors, and any special certification constraints.
- Build a regulation map before answering: identify sections that are directly triggered, downstream-triggered, or commonly scrutinized by FAA/DER/ODA reviewers.
- If the request involves cabin or seating changes, explicitly consider 25.561, 25.562, 25.567, 25.785, 25.795, 25.803, 25.807, 25.813, 25.853, and any system-safety or installation rules that the change activates.
- If the request involves structural modification, reason through load paths, attachment integrity, substantiation, and whether amended stress analysis or test evidence is needed.
- If the request involves fire or interior materials, separate flammability compliance from heat-release, smoke, toxicity, or special-condition reasoning when applicable.
- If the request involves electrical or equipment changes, reason through failure conditions, segregation, power supply effects, and system safety assessment expectations.
- Resolve overlapping or conflicting requirements using regulatory hierarchy, certification basis rules, and equivalent level of safety logic when applicable.
- Identify what will actually trigger FAA/Transport Canada scrutiny, what can fail certification, and what evidence is typically expected.
- Convert requirements into action: analyses, tests, demonstrations, conformity items, substantiation packages, and approval steps.
- Think in program terms, not just section terms: aircraft configuration, passenger count, seat/monument/layout changes, STC scope, and downstream compliance impacts.

Output rules:
- Use a fixed structure with clear headings.
- Start with the direct decision or recommendation.
- Include a short decision sentence such as "Likely STC", "Likely minor change", or "Further basis data needed" before the detailed analysis.
- Then provide **Applicable Regulations (Detailed Law Requirements)**.
    For each cited section, include:
    - legal status (mandatory regulation vs guidance/policy/interpretation),
    - exact scope trigger (why this section is activated by the scenario),
    - specific legal requirements (conditions, thresholds, sub-paragraph obligations),
    - required means of compliance (test/analysis/inspection/demo),
    - common certification evidence expected by FAA/DER/ODA.
- Then explain the impact/why each regulation applies.
- Then list risks, failure points, and likely FAA/DER questions.
- Then give the compliance approach with tests, analyses, demonstrations, and documents.
- Tailor the compliance approach to private/business-jet modification programs (cabin reconfiguration, seating changes, monument/galley/lav updates, avionics/interior/electrical changes).
- Do not provide a short or generic law list; include section-level detail sufficient for implementation.
- Keep the response traceable and professional.
- Use plain-language references in the answer; do not use internal citation tokens in the prose.
    The source list is handled separately by the application UI.
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

_GENERIC_PATTERNS = [
    r"it depends on (the )?specific",
    r"consult (the )?(faa|authority|applicant)",
    r"additional analysis may be required",
    r"further review is needed",
    r"consider applicable regulations",
    r"as applicable",
    r"generally speaking",
]

_INTRO_PATTERNS = [
    r"^(As |I am |I'm )(an? )?(AI|language model|assistant|GLM|chatbot)[^.]*\.",
    r"^(Hello|Hi)[!,]?\s+(I('m| am)|my name is)[^.]*\.",
]

_HF_DEFAULT_MODEL = "Qwen/Qwen2.5-72B-Instruct"
_NV_DEFAULT_MODEL = "meta/llama-4-maverick-17b-128e-instruct"
_ANTHROPIC_DEFAULT_MODEL = "claude-3-5-sonnet-latest"

# Per-call timeout (seconds). Two calls max = 2 × 25 = 50s, safely under nginx 60s limit.
_CALL_TIMEOUT = 25


def _is_refusal(text: str) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in _REFUSAL_PATTERNS)


def _is_low_quality_answer(text: str) -> bool:
    lower = text.lower()

    # Require substantive structure and depth, not generic short replies.
    required_markers = [
        "direct decision",
        "applicable regulations",
        "impact",
        "risks",
        "compliance approach",
    ]
    has_structure = sum(1 for m in required_markers if m in lower) >= 3
    too_short = len(text.strip()) < 1200

    generic_hits = sum(1 for p in _GENERIC_PATTERNS if re.search(p, lower))
    overly_generic = generic_hits >= 2

    return (too_short and not has_structure) or overly_generic


def _strip_intro(text: str) -> str:
    for p in _INTRO_PATTERNS:
        text = re.sub(p, "", text, flags=re.IGNORECASE | re.MULTILINE).lstrip()
    return text


def _looks_like_nvapi_model(model: str) -> bool:
    lowered = (model or "").lower()
    return any(token in lowered for token in ["meta/llama", "llama-4", "maverick"])


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

        anthropic_key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        anthropic_base_url = settings.anthropic_base_url or os.getenv("ANTHROPIC_BASE_URL", "")
        anthropic_model = settings.anthropic_model or os.getenv("ANTHROPIC_MODEL", "")

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

        # Legacy Lightning endpoints should not win when the configured model is clearly NVAPI-based.
        elif "lightning.ai" in base_url.lower() and api_key and _looks_like_nvapi_model(model):
            base_url = nvapi_base_url or "https://integrate.api.nvidia.com/v1"

        # If the base URL is still a legacy Lightning endpoint, prefer the newer providers instead.
        elif "lightning.ai" in base_url.lower():
            if hf_token:
                base_url = hf_base_url or "https://router.huggingface.co/v1"
                api_key = hf_token
                model = hf_model or _HF_DEFAULT_MODEL
            elif api_key and _looks_like_nvapi_model(model):
                base_url = nvapi_base_url or "https://integrate.api.nvidia.com/v1"
            else:
                base_url = nvapi_base_url or base_url

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
        self._provider_candidates = self._build_provider_candidates(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            nvapi_base_url=nvapi_base_url,
            nvapi_key=nvapi_key,
            nvapi_model=nvapi_model,
            hf_base_url=hf_base_url,
            hf_token=hf_token,
            hf_model=hf_model,
            anthropic_base_url=anthropic_base_url,
            anthropic_key=anthropic_key,
            anthropic_model=anthropic_model,
            litai_base_url=litai_base_url,
            litai_key=litai_key,
            litai_model=litai_model,
        )

    def _build_provider_candidates(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        nvapi_base_url: str,
        nvapi_key: str,
        nvapi_model: str,
        hf_base_url: str,
        hf_token: str,
        hf_model: str,
        anthropic_base_url: str,
        anthropic_key: str,
        anthropic_model: str,
        litai_base_url: str,
        litai_key: str,
        litai_model: str,
    ) -> list[tuple[str, str, str, str]]:
        providers: list[tuple[str, str, str, str]] = []

        if nvapi_key:
            providers.append(
                (
                    "nvapi",
                    nvapi_base_url or "https://integrate.api.nvidia.com/v1",
                    nvapi_key,
                    nvapi_model or _NV_DEFAULT_MODEL,
                )
            )

        if anthropic_key:
            providers.append(
                (
                    "anthropic",
                    anthropic_base_url or "https://api.anthropic.com",
                    anthropic_key,
                    anthropic_model or _ANTHROPIC_DEFAULT_MODEL,
                )
            )

        if hf_token:
            providers.append(
                (
                    "hf",
                    hf_base_url or "https://router.huggingface.co/v1",
                    hf_token,
                    hf_model or _HF_DEFAULT_MODEL,
                )
            )

        if litai_key:
            providers.append(
                (
                    "litai",
                    litai_base_url or base_url,
                    litai_key,
                    litai_model or model,
                )
            )

        if api_key and "lightning.ai" not in base_url.lower():
            providers.append(("legacy", base_url, api_key, model))

        return providers

    @staticmethod
    def _endpoints_for(base_url: str) -> list[str]:
        # Support both bases that already include /v1 and ones that don't.
        if base_url.endswith("/v1"):
            return [f"{base_url}/chat/completions", f"{base_url}/completions"]
        return [
            f"{base_url}/chat/completions",
            f"{base_url}/v1/chat/completions",
            f"{base_url}/completions",
            f"{base_url}/v1/completions",
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

    async def _call_async(
        self,
        messages: list[dict],
        client: httpx.AsyncClient,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        model: str,
    ) -> str:
        if provider_name == "anthropic":
            return await self._call_anthropic_async(messages, client, base_url=base_url, api_key=api_key, model=model)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": model, "messages": messages, "temperature": 0.0}
        alt_messages = [
            {
                **m,
                "content": [{"type": "text", "text": m["content"]}]
                if isinstance(m["content"], str)
                else m["content"],
            }
            for m in messages
        ]
        alt_payload = {"model": model, "messages": alt_messages, "temperature": 0.0}

        last_error: Exception | None = None

        for url in self._endpoints_for(base_url):
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

    async def _call_anthropic_async(
        self,
        messages: list[dict],
        client: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str,
        model: str,
    ) -> str:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        system_text = "\n\n".join(
            str(m.get("content", "")) for m in messages if m.get("role") == "system"
        ).strip()
        user_turns = [m for m in messages if m.get("role") in {"user", "assistant"}]
        if not user_turns:
            user_turns = [{"role": "user", "content": "Please answer the question directly."}]

        anth_messages = [
            {
                "role": "assistant" if m["role"] == "assistant" else "user",
                "content": [{"type": "text", "text": str(m.get("content", ""))}],
            }
            for m in user_turns
        ]

        payload = {
            "model": model,
            "max_tokens": 1200,
            "temperature": 0.0,
            "messages": anth_messages,
        }
        if system_text:
            payload["system"] = system_text

        resp = await client.post(f"{base_url.rstrip('/')}/v1/messages", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content") or []
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                text_parts.append(str(item["text"]))
        answer = "\n".join(text_parts).strip()
        if not answer:
            raise RuntimeError("Anthropic response did not include textual content.")
        return answer

    async def chat_async(self, user_prompt: str, history: list[dict] | None = None) -> str:
        if not self.api_key:
            return (
                "LLM is not configured. Set one of: "
                "NVAPI_KEY, AI_GAMMA4_KEY, LLM_API_KEY, LITAI_API_KEY, or HF_TOKEN/HF_API_TOKEN."
            )

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for turn in history or []:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_prompt})

        async with httpx.AsyncClient(timeout=_CALL_TIMEOUT) as client:
            last_error: Exception | None = None
            for provider_name, base_url, api_key, model in self._provider_candidates:
                try:
                    answer = await self._call_async(
                        messages,
                        client,
                        provider_name=provider_name,
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                    )

                    # If the model refused or produced an empty response, force a direct retry.
                    if _is_refusal(answer) or len(answer.strip()) < 24:
                        retry_messages = [
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
                        answer = await self._call_async(
                            retry_messages,
                            client,
                            provider_name=provider_name,
                            base_url=base_url,
                            api_key=api_key,
                            model=model,
                        )

                    if _is_low_quality_answer(answer):
                        quality_retry_messages = [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                            {"role": "assistant", "content": answer},
                            {
                                "role": "user",
                                "content": (
                                    "Rewrite the answer with higher precision and non-generic engineering detail. "
                                    "Do not give broad statements. Provide section-level legal requirements, "
                                    "explicit triggers, concrete compliance evidence, likely FAA scrutiny points, "
                                    "and private-jet modification context. "
                                    "Keep headings: Direct Decision, Applicable Regulations (Detailed Law Requirements), "
                                    "Impact Explanation, Risks / Failure Points, Compliance Approach. "
                                    "Do not include an Action Steps section."
                                ),
                            },
                        ]
                        answer = await self._call_async(
                            quality_retry_messages,
                            client,
                            provider_name=provider_name,
                            base_url=base_url,
                            api_key=api_key,
                            model=model,
                        )

                    cleaned = _strip_intro(answer)
                    if cleaned:
                        return cleaned
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    continue

            if last_error is not None:
                return f"The model request failed. Please try again.\n\n⚠ {last_error}"
            return "I could not generate a usable answer for this query."

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
