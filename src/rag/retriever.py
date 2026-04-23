from __future__ import annotations

from datetime import date
import re

from src.config import settings
from src.indexing.vector_store import LocalVectorStore
from src.models import RetrievedChunk
from src.rag.versioning import build_query_version_hint, parse_issue_date


class Retriever:
    def __init__(self, store: LocalVectorStore):
        self.store = store

    def _version_bonus(self, chunk_issue_date: str | None, requested_date: date | None) -> float:
        if requested_date is None:
            return 0.0

        issue_date = parse_issue_date(chunk_issue_date)
        if issue_date is None:
            return -0.03

        delta_days = (requested_date - issue_date).days
        if delta_days < 0:
            return -0.08
        if delta_days == 0:
            return 0.08
        if delta_days <= 365:
            return 0.05
        if delta_days <= 3 * 365:
            return 0.02
        return -0.02

    def _source_bonus(self, source_id: str, query: str) -> float:
        text = query.lower()
        if any(token in text for token in ["car 525", "transport canada", "canadian aviation"]):
            if source_id == "tc_car_525":
                return 0.10
            if source_id.startswith("faa_ecfr"):
                return -0.03

        if any(token in text for token in ["part 25", "part 21", "title 14", "cfr", "federal aviation administration", "faa"]):
            if source_id == "faa_ecfr_title14_full":
                return 0.10
            if source_id == "faa_ecfr_part25_fallback":
                return 0.06
            if source_id == "faa_advisory_circulars":
                return 0.01

        if "advisory circular" in text or "ac " in text:
            if source_id == "faa_advisory_circulars":
                return 0.10
            if source_id.startswith("faa_ecfr"):
                return -0.02

        return 0.0

    def _query_hints(self, query: str) -> dict[str, bool]:
        q = query.lower()
        return {
            "mentions_part23": bool(re.search(r"\bpart\s*23\b|\b23\.\d+", q)),
            "mentions_part25": bool(re.search(r"\bpart\s*25\b|\b25\.\d+|\btype\s*iii\b", q)),
            "mentions_part121": bool(re.search(r"\bpart\s*121\b|\b121\.\d+", q)),
            "mentions_part135": bool(re.search(r"\bpart\s*135\b|\b135\.\d+", q)),
            "private_jet_context": any(
                token in q
                for token in ["private jet", "business jet", "corporate jet", "cabin modification", "stc", "interior mod", "divan", "monument"]
            ),
        }

    def _part_penalty(self, query: str, chunk) -> float:
        hints = self._query_hints(query)
        section_path = (chunk.section_path or "").lower()
        title = (chunk.title or "").lower()
        text = f"{section_path} {title}"

        in_part23 = "part 23" in text or re.search(r"\b23\.\d+", text) is not None
        in_part25 = "part 25" in text or re.search(r"\b25\.\d+", text) is not None
        in_part121 = "part 121" in text or re.search(r"\b121\.\d+", text) is not None
        in_part135 = "part 135" in text or re.search(r"\b135\.\d+", text) is not None

        penalty = 0.0

        # Private/business-jet modification queries are usually certification-basis (Part 25/23)
        # and should not be polluted by airline/operator rules (Part 121/135) unless explicitly asked.
        if hints["private_jet_context"] or hints["mentions_part25"]:
            if in_part121 and not hints["mentions_part121"]:
                penalty -= 0.28
            if in_part135 and not hints["mentions_part135"]:
                penalty -= 0.22

        if hints["mentions_part25"]:
            if in_part23 and not hints["mentions_part23"]:
                penalty -= 0.20
            if in_part25:
                penalty += 0.06

        if hints["mentions_part23"]:
            if in_part25 and not hints["mentions_part25"]:
                penalty -= 0.20
            if in_part23:
                penalty += 0.06

        return penalty

    def _section_key(self, chunk) -> str:
        text = f"{chunk.section_path or ''} {chunk.title or ''}".lower()
        match = re.search(r"\b((?:23|25|121|135)\.\d+[a-z]?)\b", text)
        if match:
            return match.group(1)
        return chunk.chunk_id

    def _extract_cited_sections(self, query: str) -> list[str]:
        # Captures forms like "25.613" and "§25.613" from user questions.
        matches = re.findall(r"(?:§\s*)?(25\.\d+[a-z]?)", query, flags=re.IGNORECASE)
        return sorted({m.lower() for m in matches})

    def _chunk_bonus(self, query: str, chunk) -> float:
        score = 0.0
        q = query.lower()
        section_path = (chunk.section_path or "").lower()
        title = (chunk.title or "").lower()
        page_url = (chunk.page_url or "").lower()
        text = (chunk.text or "").lower()

        cited_sections = self._extract_cited_sections(query)
        if cited_sections:
            matched_section = any(
                s in section_path or s in title or s in text for s in cited_sections
            )
            if matched_section:
                score += 0.22
            elif chunk.source_id in {"faa_ecfr_title14_full", "faa_ecfr_part25_fallback", "faa_far_part25"}:
                score += 0.04
            else:
                score -= 0.10

        if "amendment" in q and chunk.source_id == "faa_far_part25":
            score += 0.12

        # Advisory search listing pages are broad index pages and tend to outrank true regulatory text.
        if chunk.source_id == "faa_advisory_circulars":
            if "search results" in section_path or "search results" in title:
                score -= 0.28
            if "/document.list" in page_url:
                score -= 0.18

        return score

    def _section_target_candidates(self, query: str, top_k: int) -> list[RetrievedChunk]:
        cited_sections = self._extract_cited_sections(query)
        if not cited_sections:
            return []

        candidates: list[RetrievedChunk] = []
        for chunk in self.store.chunks:
            section_path = (chunk.section_path or "").lower()
            title = (chunk.title or "").lower()
            text = (chunk.text or "").lower()
            if not any(s in section_path or s in title or s in text for s in cited_sections):
                continue

            score = 0.60
            if chunk.source_id in {"faa_ecfr_title14_full", "faa_ecfr_part25_fallback", "faa_far_part25"}:
                score += 0.14
            if "section" in section_path or "part 25" in section_path:
                score += 0.06

            candidates.append(RetrievedChunk(chunk=chunk, score=score))

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[: max(top_k, 8)]

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        k = top_k or settings.top_k
        hint = build_query_version_hint(query)
        candidate_k = max(k * 4, 24)
        results = self.store.search(query, top_k=candidate_k)
        results.extend(self._section_target_candidates(query, top_k=candidate_k))

        # Merge semantic and section-targeted candidates by chunk id.
        merged: dict[str, RetrievedChunk] = {}
        for item in results:
            existing = merged.get(item.chunk.chunk_id)
            if existing is None or item.score > existing.score:
                merged[item.chunk.chunk_id] = item

        scored: list[RetrievedChunk] = []
        for item in merged.values():
            adjusted = item.score + self._version_bonus(item.chunk.issue_date, hint.requested_date)
            adjusted += self._source_bonus(item.chunk.source_id, query)
            adjusted += self._chunk_bonus(query, item.chunk)
            adjusted += self._part_penalty(query, item.chunk)
            scored.append(RetrievedChunk(chunk=item.chunk, score=adjusted))

        scored.sort(key=lambda item: item.score, reverse=True)

        # De-duplicate by regulation section so top_k doesn't get consumed by near-identical variants.
        deduped: list[RetrievedChunk] = []
        seen_keys: set[str] = set()
        for item in scored:
            key = self._section_key(item.chunk)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)
            if len(deduped) >= candidate_k:
                break

        hints = self._query_hints(query)
        dynamic_min_relevance = settings.min_relevance
        if hints["private_jet_context"] or hints["mentions_part25"] or hints["mentions_part23"]:
            dynamic_min_relevance = max(settings.min_relevance, 0.24)

        filtered = [r for r in deduped[:k] if r.score >= dynamic_min_relevance]
        if filtered:
            return filtered

        # Fallback: do not return empty context; keep best candidates for grounding.
        fallback_count = min(max(4, k // 2), len(deduped))
        return deduped[:fallback_count]
