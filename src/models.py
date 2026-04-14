from dataclasses import dataclass
from typing import Any


@dataclass
class SectionDocument:
    source_id: str
    source_url: str
    page_url: str
    section_path: str
    title: str
    content: str
    issue_date: str | None = None


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source_id: str
    source_url: str
    page_url: str
    section_path: str
    title: str
    issue_date: str | None = None


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float


@dataclass
class AnswerResult:
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    grounded: bool
