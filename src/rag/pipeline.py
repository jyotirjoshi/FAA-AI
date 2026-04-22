import re
from urllib.parse import urlparse

from src.models import AnswerResult
from src.rag.llm import LLMClient
from src.rag.retriever import Retriever
from src.rag.versioning import build_query_version_hint


def _build_excerpt(text: str, limit: int = 2200) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    cleaned = "\n".join(lines).strip()

    if not cleaned:
        cleaned = re.sub(r"\s+", " ", text or "").strip()

    if not cleaned:
        return ""

    if len(cleaned) <= limit:
        return cleaned

    cut = cleaned.rfind(".", 0, limit)
    if cut < max(180, limit // 2):
        cut = cleaned.rfind(" ", 0, limit)
    if cut < 0:
        cut = limit
    return cleaned[:cut].rstrip() + "..."


def _is_xmlish_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return lowered.endswith(".xml") or ".xml?" in lowered or "/full/" in lowered


def _humanize_source_id(source_id: str | None) -> str:
    sid = (source_id or "").strip().lower()
    if not sid:
        return "Regulatory Source"
    if sid.startswith("pdf_"):
        return (source_id or "").strip()[4:].replace("_", " ")
    if "faa_far_part25" in sid:
        return "FAA FAR Part 25"
    if "faa_ecfr" in sid:
        return "FAA eCFR Title 14"
    if "advisory" in sid:
        return "FAA Advisory Circulars"
    if "tc_car_525" in sid:
        return "Transport Canada CAR 525"
    return (source_id or "").replace("_", " ").strip().title()


def _source_host_label(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    host = host.replace("www.", "")
    if "ecfr.gov" in host:
        return "eCFR"
    if "faa.gov" in host:
        return "FAA"
    if "drs.faa.gov" in host:
        return "FAA DRS"
    if "tc.canada.ca" in host:
        return "Transport Canada"
    return host


def _extract_section_number(section_path: str | None, title: str | None) -> str | None:
    haystacks = [section_path or "", title or ""]
    patterns = [
        r"§\s*([0-9]+\.[0-9]+[a-z0-9\-]*)",
        r"\b([0-9]+\.[0-9]+[a-z0-9\-]*)\b",
    ]
    for text in haystacks:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
    return None


def _build_ecfr_section_url(section_path: str | None, title: str | None, issue_date: str | None) -> str | None:
    section_num = _extract_section_number(section_path, title)
    if not section_num:
        return None

    # eCFR supports current and date-qualified section routes.
    if issue_date:
        return f"https://www.ecfr.gov/on/{issue_date}/title-14/section-{section_num}"
    return f"https://www.ecfr.gov/current/title-14/section-{section_num}"


def _pick_citation_url(
    source_id: str | None,
    title: str | None,
    section_path: str | None,
    issue_date: str | None,
    page_url: str | None,
    source_url: str | None,
) -> str | None:
    page = (page_url or "").strip()
    source = (source_url or "").strip()
    sid = (source_id or "").strip().lower()

    if "ecfr" in sid:
        ecfr_section_url = _build_ecfr_section_url(section_path, title, issue_date)
        if ecfr_section_url:
            return ecfr_section_url

    if _is_xmlish_url(page):
        return source or None
    return page or source or None


def _build_citation(cid: str, item) -> dict:
    source_label = _humanize_source_id(item.chunk.source_id)
    source_url = (item.chunk.source_url or "").strip() or None
    page_url = (item.chunk.page_url or "").strip() or None
    display_url = _pick_citation_url(
        item.chunk.source_id,
        item.chunk.title,
        item.chunk.section_path,
        item.chunk.issue_date,
        page_url,
        source_url,
    )
    host_label = _source_host_label(display_url)
    return {
        "id": cid,
        "title": item.chunk.title,
        "section_path": item.chunk.section_path,
        "url": display_url,
        "source": source_label,
        "source_url": source_url,
        "page_url": page_url,
        "source_host": host_label,
        "issue_date": item.chunk.issue_date,
        "score": round(item.score, 4),
        "excerpt": _build_excerpt(item.chunk.text),
    }


class RagPipeline:
    def __init__(self, retriever: Retriever, llm: LLMClient):
        self.retriever = retriever
        self.llm = llm

    def _build_answer_prompt(self, question: str, retrieved: list) -> tuple[str, list[dict]]:
        version_hint = build_query_version_hint(question)
        context_lines: list[str] = []
        citations: list[dict] = []
        for idx, item in enumerate(retrieved, start=1):
            cid = f"C{idx}"
            context_lines.append(
                f"[{cid}] title={item.chunk.title}\nsection_path={item.chunk.section_path}\nurl={item.chunk.page_url}\nissue_date={item.chunk.issue_date or 'unknown'}\ntext={item.chunk.text}\n"
            )
            citations.append(_build_citation(cid, item))

        context_block = "\n".join(context_lines) if context_lines else "(No indexed snippets matched — answer entirely from your regulatory knowledge.)"

        prompt = (
            "Question:\n"
            f"{question}\n\n"
            f"Version guidance: use the {('requested historical date' if version_hint.requested_date else 'latest/current law')} unless the context explicitly supports a different version. If the law has changed over time, mention the issue_date from the supporting citation and note whether you are citing current or historical text.{' If the user is asking what changed, explicitly compare the historical and current versions and summarize the change in plain language.' if version_hint.wants_change_summary else ''}\n\n"
            "Context snippets (use as primary source, cite with [C#]):\n"
            f"{context_block}\n\n"
            "Instructions:\n"
            "- Answer the question fully and in detail.\n"
            "- For every regulation section mentioned or relevant, explain WHAT IT ACTUALLY REQUIRES — include load conditions, thresholds, sub-paragraphs, and test criteria where applicable.\n"
            "- If a snippet only references a section without reproducing its text, supplement with your knowledge of that section's actual requirements and note: '(from regulation knowledge)'.\n"
            "- Cite snippets with [C#] for any claim supported by retrieved context.\n"
            "- Do NOT say you cannot answer — always provide a complete, detailed response.\n"
            "- Use structured markdown with clear headings for multi-part answers."
        )
        return prompt, citations

    def _build_compliance_prompt(
        self,
        renovation_request: str,
        tcds_text: str,
        governing_body_hint: str | None,
        retrieved: list,
    ) -> tuple[str, list[dict]]:
        version_hint = build_query_version_hint(f"{renovation_request} {tcds_text}")
        context_lines: list[str] = []
        citations: list[dict] = []
        for idx, item in enumerate(retrieved, start=1):
            cid = f"C{idx}"
            context_lines.append(
                f"[{cid}] title={item.chunk.title}\nsection_path={item.chunk.section_path}\nurl={item.chunk.page_url}\nsource={item.chunk.source_id}\nissue_date={item.chunk.issue_date or 'unknown'}\ntext={item.chunk.text}\n"
            )
            citations.append(_build_citation(cid, item))

        context_block = "\n".join(context_lines) if context_lines else "(No indexed snippets matched — answer entirely from your regulatory knowledge.)"
        hint_text = governing_body_hint or "not provided"
        prompt = (
            "You are building a certification compliance plan for aircraft renovation.\n"
            "Inputs:\n"
            f"1) Renovation request: {renovation_request}\n"
            f"2) TCDS details: {tcds_text}\n"
            f"3) Governing body hint: {hint_text}\n\n"
            "Context snippets (use as primary source, cite with [C#]):\n"
            f"{context_block}\n\n"
            "Output requirements:\n"
            "- Decide governing body (FAA or Transport Canada) using context + TCDS.\n"
            "- Identify likely regulatory part(s), especially Part 25 / Chapter 525 when applicable.\n"
            "- List candidate sections affected by this renovation with rationale, including a summary of what each section actually requires.\n"
            "- For any section referenced in the snippets but without full text, explain the section's actual requirements from your regulatory knowledge and label it '(from regulation knowledge)'.\n"
            "- Include effective date / historical version considerations for each section.\n"
            f"- If multiple issue dates are present, explain what changed between the historical and current versions.{' If the user specifically asks what changed, present the comparison as a short delta list.' if version_hint.wants_change_summary else ''}\n"
            "- If exact effective date is not in retrieved evidence, use your knowledge and clearly state the source.\n"
            "- For every claim backed by a retrieved snippet, attach [C#] citations.\n"
            "- Return response in structured markdown with headings: Governing Body, Applicable Parts, Candidate Sections, Effective Date Checks, Open Gaps, Draft Compliance Plan."
        )
        return prompt, citations

    # ── Async (used by FastAPI endpoints) ──

    async def answer_async(
        self,
        question: str,
        history: list[dict] | None = None,
    ) -> AnswerResult:
        retrieved = self.retriever.retrieve(question)
        prompt, citations = self._build_answer_prompt(question, retrieved)
        answer = await self.llm.chat_async(prompt, history=history)
        best = max((c["score"] for c in citations), default=0.0)
        return AnswerResult(
            answer=answer,
            citations=citations,
            confidence=min(float(best), 1.0),
            grounded=bool(answer and len(answer.strip()) > 20),
        )

    async def compliance_plan_async(
        self,
        renovation_request: str,
        tcds_text: str,
        governing_body_hint: str | None = None,
    ) -> AnswerResult:
        combined_query = (
            f"Renovation request: {renovation_request}\n"
            f"TCDS certification basis and aircraft model details: {tcds_text}\n"
            "Find governing regulation body, applicable part, relevant sections, and effective/historical versions."
        )
        retrieved = self.retriever.retrieve(combined_query)
        prompt, citations = self._build_compliance_prompt(
            renovation_request, tcds_text, governing_body_hint, retrieved
        )
        answer = await self.llm.chat_async(prompt)
        best = max((c["score"] for c in citations), default=0.0)
        return AnswerResult(
            answer=answer,
            citations=citations,
            confidence=min(float(best), 1.0),
            grounded=bool(answer and len(answer.strip()) > 20),
        )

    # ── Sync wrappers (kept for backward compatibility) ──

    def answer(self, question: str) -> AnswerResult:
        retrieved = self.retriever.retrieve(question)
        prompt, citations = self._build_answer_prompt(question, retrieved)
        answer = self.llm.chat(prompt)
        best = max((c["score"] for c in citations), default=0.0)
        return AnswerResult(
            answer=answer,
            citations=citations,
            confidence=min(float(best), 1.0),
            grounded=bool(answer and len(answer.strip()) > 20),
        )

    def compliance_plan(
        self,
        renovation_request: str,
        tcds_text: str,
        governing_body_hint: str | None = None,
    ) -> AnswerResult:
        combined_query = (
            f"Renovation request: {renovation_request}\n"
            f"TCDS certification basis and aircraft model details: {tcds_text}\n"
            "Find governing regulation body, applicable part, relevant sections, and effective/historical versions."
        )
        retrieved = self.retriever.retrieve(combined_query)
        prompt, citations = self._build_compliance_prompt(
            renovation_request, tcds_text, governing_body_hint, retrieved
        )
        answer = self.llm.chat(prompt)
        best = max((c["score"] for c in citations), default=0.0)
        return AnswerResult(
            answer=answer,
            citations=citations,
            confidence=min(float(best), 1.0),
            grounded=bool(answer and len(answer.strip()) > 20),
        )
