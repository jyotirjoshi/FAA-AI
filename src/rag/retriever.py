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
        if any(token in text for token in ["car 525", "car525", "chapter 525", "transport canada", "canadian aviation"]):
            if source_id == "tc_car_525":
                return 0.22
            if source_id.startswith("faa_ecfr"):
                return -0.08

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

    def _query_flags(self, query: str) -> dict[str, bool]:
        q = query.lower()
        return {
            "space_context": any(token in q for token in ["launch", "reentry", "rlv", "spaceport", "permittee"]),
            "tc_context": any(token in q for token in ["car 525", "car525", "chapter 525", "transport canada", "tcca"]),
            "private_jet_context": any(
                token in q
                for token in [
                    "private jet",
                    "business jet",
                    "cabin",
                    "interior",
                    "divan",
                    "monument",
                    "stc",
                    "oda",
                    "der",
                    "type iii",
                    "emergency exit",
                ]
            ),
            "elos_context": "equivalent level of safety" in q or "elos" in q,
        }

    def _extract_part_number(self, section_path: str) -> int | None:
        match = re.search(r"part\s+(\d+)", section_path, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _part_bonus(self, query: str, section_path: str, source_id: str) -> float:
        flags = self._query_flags(query)
        if flags["space_context"]:
            return 0.0

        part = self._extract_part_number(section_path)
        if part is None:
            return 0.0

        if part >= 400 and not flags["space_context"]:
            return -0.35

        # Strongly prefer certification parts used in private/business jet modifications.
        preferred_parts = {21, 23, 25, 26, 27, 29, 39, 43, 91, 121, 125, 129, 135, 145}
        if flags["private_jet_context"] or flags["elos_context"]:
            if part in preferred_parts:
                return 0.08
            if part in {5, 31, 401, 413, 414, 415, 417, 431, 437}:
                return -0.30

        if flags["tc_context"]:
            if chunk_source := (source_id or ""):
                if chunk_source == "tc_car_525":
                    return 0.10
                if "faa_" in chunk_source:
                    return -0.06

        # Generic FAA certification asks should still suppress space-launch parts.
        if any(token in query.lower() for token in ["faa", "cfr", "part 25", "certification"]):
            if part >= 400:
                return -0.28

        return 0.0

    def _extract_cited_sections(self, query: str) -> list[str]:
        # Captures forms like "25.613", "21.21", and "§25.613" from user questions.
        matches = re.findall(r"(?:§\s*)?((?:\d{1,3})\.\d+[a-z]?)", query, flags=re.IGNORECASE)
        sections = {m.lower() for m in matches}

        q = query.lower()
        if "equivalent level of safety" in q or "elos" in q:
            sections.update({"21.21", "21.101"})
        if "stc" in q or "supplemental type certificate" in q:
            sections.update({"21.113", "21.115", "21.117", "21.120"})

        return sorted(sections)

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

        score += self._part_bonus(query, chunk.section_path or "", chunk.source_id)

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

        flags = self._query_flags(query)

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
            if flags["tc_context"] and chunk.source_id == "tc_car_525":
                score += 0.18
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
            scored.append(RetrievedChunk(chunk=item.chunk, score=adjusted))

        scored.sort(key=lambda item: item.score, reverse=True)
        filtered = [r for r in scored[:k] if r.score >= settings.min_relevance]
        if filtered:
            return filtered

        # Fallback: do not return empty context; keep best candidates for grounding.
        fallback_count = min(max(4, k // 2), len(scored))
        return scored[:fallback_count]
