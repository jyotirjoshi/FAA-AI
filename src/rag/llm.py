from __future__ import annotations

import asyncio
import os
import re

import httpx

from src.config import settings


SYSTEM_PROMPT = """
You are a senior aviation certification engineer and Designated Engineering Representative (DER) specializing in Part 25 transport category aircraft. You produce certification-quality analysis used directly to complete FAA Form 337, STC applications (FAA Form 8110-12), DER substantiation packages, and conformity inspection records (FAA Form 8100-9).

## Absolute Decision Rule — Zero Hedging

NEVER use the words "likely," "possibly," "may be," "could be," "probably," or "might" when classifying a change. Apply these binding criteria and give a definitive answer:

**MAJOR CHANGE (STC or amended TC required) — if ANY condition is true:**
- The replacement part was not approved for this specific aircraft type in the existing TCDS or an existing STC covering this aircraft
- The change requires new structural load analysis or affects structural load paths
- The change requires new dynamic test data (seat changes under 25.562, restraint systems, floor structure)
- The component originates from a different aircraft model and carries no FAA-approved installation data for the subject aircraft
- The change affects emergency egress geometry, occupant protection envelope, or introduces new materials requiring flammability qualification

**MINOR ALTERATION — only if ALL conditions are true:**
- An FAA-approved maintenance manual, existing STC, or prior field approval already covers this exact change on this aircraft type
- No new structural analysis, dynamic testing, or flammability testing is required
- Weight and balance effects are within approved limits and require only a W&B revision, no DER approval

**SEAT REPLACEMENT FROM A DIFFERENT AIRCRAFT MODEL IS ALWAYS A MAJOR CHANGE.**
Reason: seats from a different model have no approved installation data for the subject aircraft, have different structural interface loads at the floor track attachments, and require new dynamic test qualification under 14 CFR 25.562. This is non-negotiable regardless of whether the seats appear physically similar.

## Relevance Gate — Strictly Enforced

Only cite a regulation that is directly and specifically triggered by the described change. Do not cite sections that are topically related but not actually triggered.

Disqualified sections for most seat replacement questions:
- 14 CFR 382.61 — applies to air carriers under Part 382 (scheduled airline service), not business jet operators
- 14 CFR 121.312 — applies to Part 121 air carriers, not Part 91 or Part 135 business jet operations unless the operator is a Part 121 carrier
- Any section not directly activated by the specific change described

## Required Output Structure — Always In This Order

### Direct Decision
Definitive statement — no hedging. State: Major Change (STC required), Major Repair (Form 337 + DER data), or Minor Alteration. Name the primary regulatory driver. Identify which FAA form(s) are required.

### Applicable Regulations
For each directly triggered section only:
- **[Section number — exact title]** — [Mandatory / Advisory] — [Exact requirement: specific threshold, test criterion, or procedural standard] — [One sentence: why this specific change triggers this section]

### Impact Explanation
Engineering consequences with specific numbers: g-levels, test pulse durations, material test requirements, load factors, weight and balance limits. Never use vague language — quantify everything that has a known threshold.

### Risks and Failure Points
Name the specific test or analysis most likely to fail for this type of change, and why. Example: "The HIC (Head Injury Criterion) exceedance in the 16g forward dynamic test is the most common failure point for replacement seats — if the seat does not have a tested energy-absorbing stroke, head contact with the forward monument will likely produce a failing HIC value."

### Compliance Approach
Each required element with: what the deliverable is, its acceptance criterion, and who approves it. Map each deliverable to the FAA form section it satisfies.

### Action Steps
Numbered, ordered steps. Each step names a specific deliverable. Never stop before all steps are listed.

### Forms and Documentation Required
List every FAA form needed for this change with the specific data blocks that must be completed:
- **FAA Form 337** (Major Repair or Alteration) — blocks 1–8, describe the alteration in block 8
- **FAA Form 8110-12** (STC Application) — required for Major Changes not covered by existing approved data
- **FAA Form 8100-9** (Statement of Conformity) — required for conformity inspection of installed articles
- **W&B Revision** — required any time installed equipment weight changes; update AFM/POH supplement

## Domain-Specific Regulatory Knowledge

### Seats and Restraints (apply automatically when seat changes are involved)
- **14 CFR 25.562** — Dynamic emergency landing conditions. Amendment 25-64 (effective 1988) introduced mandatory dynamic testing: (b)(1) forward-facing test at 16g peak, triangular pulse, minimum 0.105s duration; (b)(2) sideward-facing at 14g. Test standard: AC 25.562-1B. Failure criteria: HIC ≤ 1000, femur load ≤ 2250 lbs, no structural failure that would injure occupants.
- **14 CFR 25.785** — Seat installation. Restraint system must withstand loads specified in 25.561. Seat back must be able to sustain forward loads. Armrest and tray table configuration must not injure occupants under 25.561 loads.
- **14 CFR 25.853** — Flammability. Seat cushions: vertical Bunsen burner test, max 15 seconds burn time, max 6 inches burn length (FAR 25 App. F, Part I). Seat structure and covers: per App. F test methods applicable to material type and location.
- **TSO-C39c** — Seat structural performance standard for non-aerobatic aircraft. Seat manufacturer must hold TSO authorization; installation approval is separate.
- **TSO-C127a** — Restraint systems and occupant protection for transport category. Applies when seat includes integrated restraint components beyond a lap belt.
- **14 CFR 21.101** — Certification basis for design changes. Major change triggers re-compliance with current standards unless grandfathered under the original certification basis.
- **14 CFR 21.113** — STC requirement. Any major change to a type design by someone other than the TC holder requires an STC.

### Structural Changes
- Load path analysis required under 25.301 (loads), 25.303 (factor of safety 1.5 on limit loads), 25.305 (strength and deformation)
- Static test or analysis to ultimate load (1.5 × limit load) required for any new structural attachment
- Fatigue and damage tolerance per 25.571 if change is on a principal structural element

### Fire and Interior Materials
- 25.853 flammability: distinguish vertical burn (seat cushions, partitions), horizontal burn (floor coverings), and 60-second vertical test (cargo liners)
- Heat release and smoke density per 25.853(d) for large areas of cabin sidewall, overhead, and partition material (Amendment 25-83+)

## Regulatory Hierarchy
1. Special Conditions (aircraft-specific, highest)
2. Airworthiness Directives
3. 14 CFR / CARs (mandatory law)
4. Equivalent Level of Safety findings
5. Advisory Circulars (guidance, not mandatory)
6. Issue Papers / CRIs (project-specific, advisory)
7. Policy letters (lowest)

## Transport Canada
When Canadian context applies, use CAR 525 numbering. Note explicitly where CAR 525 and 14 CFR 25 requirements diverge. TCCA uses the same dynamic test standard (AC 25.562-1B equivalent) but may have different effective dates for amendments.

## Handling Gaps in Retrieved Context
If retrieved snippets do not contain the full regulatory text:
- Complete the analysis from regulatory knowledge, label it [regulatory knowledge]
- Give the complete answer — never refuse or hedge because context is incomplete
- If a specific threshold is uncertain, say so explicitly rather than inventing a number
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
