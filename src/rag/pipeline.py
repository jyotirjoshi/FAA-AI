from src.models import AnswerResult
from src.rag.llm import LLMClient
from src.rag.retriever import Retriever
from src.rag.versioning import build_query_version_hint


class RagPipeline:
    def __init__(self, retriever: Retriever, llm: LLMClient):
        self.retriever = retriever
        self.llm = llm

    def answer(self, question: str) -> AnswerResult:
        retrieved = self.retriever.retrieve(question)
        version_hint = build_query_version_hint(question)
        if not retrieved:
            return AnswerResult(
                answer="I cannot answer with sufficient certainty from the indexed sources.",
                citations=[],
                confidence=0.0,
                grounded=False,
            )

        context_lines: list[str] = []
        citations: list[dict] = []
        for idx, item in enumerate(retrieved, start=1):
            cid = f"C{idx}"
            context_lines.append(
                f"[{cid}] title={item.chunk.title}\nsection_path={item.chunk.section_path}\nurl={item.chunk.page_url}\nissue_date={item.chunk.issue_date or 'unknown'}\ntext={item.chunk.text}\n"
            )
            citations.append(
                {
                    "id": cid,
                    "title": item.chunk.title,
                    "section_path": item.chunk.section_path,
                    "url": item.chunk.page_url,
                    "source": item.chunk.source_id,
                    "issue_date": item.chunk.issue_date,
                    "score": round(item.score, 4),
                }
            )

        prompt = (
            "Question:\n"
            f"{question}\n\n"
            f"Version guidance: use the {('requested historical date' if version_hint.requested_date else 'latest/current law')} unless the context explicitly supports a different version. If the law has changed over time, mention the issue_date from the supporting citation and note whether you are citing current or historical text.{' If the user is asking what changed, explicitly compare the historical and current versions and summarize the change in plain language.' if version_hint.wants_change_summary else ''}\n\n"
            "Context snippets:\n"
            f"{'\n'.join(context_lines)}\n"
            "Instruction: produce a concise answer with explicit [C#] citation markers per claim. If multiple issue dates are present, explain the change or difference between them in plain language."
        )

        answer = self.llm.chat(prompt)
        best = max((c["score"] for c in citations), default=0.0)
        grounded = "cannot answer with sufficient certainty" not in answer.lower()

        return AnswerResult(
            answer=answer,
            citations=citations,
            confidence=min(float(best), 1.0),
            grounded=grounded,
        )

    def compliance_plan(
        self,
        renovation_request: str,
        tcds_text: str,
        governing_body_hint: str | None = None,
    ) -> AnswerResult:
        version_hint = build_query_version_hint(f"{renovation_request} {tcds_text}")
        combined_query = (
            f"Renovation request: {renovation_request}\n"
            f"TCDS certification basis and aircraft model details: {tcds_text}\n"
            "Find governing regulation body, applicable part, relevant sections, and effective/historical versions."
        )

        retrieved = self.retriever.retrieve(combined_query)
        if not retrieved:
            return AnswerResult(
                answer="I cannot answer with sufficient certainty from the indexed sources.",
                citations=[],
                confidence=0.0,
                grounded=False,
            )

        context_lines: list[str] = []
        citations: list[dict] = []
        for idx, item in enumerate(retrieved, start=1):
            cid = f"C{idx}"
            context_lines.append(
                f"[{cid}] title={item.chunk.title}\nsection_path={item.chunk.section_path}\nurl={item.chunk.page_url}\nsource={item.chunk.source_id}\nissue_date={item.chunk.issue_date or 'unknown'}\ntext={item.chunk.text}\n"
            )
            citations.append(
                {
                    "id": cid,
                    "title": item.chunk.title,
                    "section_path": item.chunk.section_path,
                    "url": item.chunk.page_url,
                    "source": item.chunk.source_id,
                    "issue_date": item.chunk.issue_date,
                    "score": round(item.score, 4),
                }
            )

        hint_text = governing_body_hint or "not provided"
        prompt = (
            "You are building a certification compliance plan for aircraft renovation.\n"
            "Inputs:\n"
            f"1) Renovation request: {renovation_request}\n"
            f"2) TCDS details: {tcds_text}\n"
            f"3) Governing body hint: {hint_text}\n\n"
            "Context snippets:\n"
            f"{'\n'.join(context_lines)}\n"
            "Output requirements:\n"
            "- Decide governing body (FAA or Transport Canada) using context + TCDS.\n"
            "- Identify likely regulatory part(s), especially Part 25 / Chapter 525 when applicable.\n"
            "- List candidate sections affected by this renovation with rationale.\n"
            "- Include effective date / historical version considerations for each section.\n"
            f"- If multiple issue dates are present, explain what changed between the historical and current versions.{' If the user specifically asks what changed, present the comparison as a short delta list.' if version_hint.wants_change_summary else ''}\n"
            "- If exact effective date is not explicit in retrieved evidence, state uncertainty clearly and abstain from guessing.\n"
            "- For every claim, attach [C#] citations.\n"
            "- Return response in structured markdown with headings: Governing Body, Applicable Parts, Candidate Sections, Effective Date Checks, Open Gaps, Draft Compliance Plan."
        )

        answer = self.llm.chat(prompt)
        best = max((c["score"] for c in citations), default=0.0)
        grounded = "cannot answer with sufficient certainty" not in answer.lower()

        return AnswerResult(
            answer=answer,
            citations=citations,
            confidence=min(float(best), 1.0),
            grounded=grounded,
        )
