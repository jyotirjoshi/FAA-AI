import hashlib
import re

from src.models import Chunk, SectionDocument


class SectionChunker:
    def __init__(self, max_chars: int = 1200, overlap: int = 200):
        self.max_chars = max_chars
        self.overlap = overlap

    def _normalize(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def chunk(self, docs: list[SectionDocument]) -> list[Chunk]:
        chunks: list[Chunk] = []

        for doc in docs:
            text = self._normalize(doc.content)
            if not text:
                continue

            start = 0
            while start < len(text):
                end = min(start + self.max_chars, len(text))
                snippet = text[start:end]
                digest = hashlib.md5(
                    f"{doc.page_url}|{doc.section_path}|{start}|{end}".encode("utf-8")
                ).hexdigest()[:16]
                chunks.append(
                    Chunk(
                        chunk_id=digest,
                        text=snippet,
                        source_id=doc.source_id,
                        source_url=doc.source_url,
                        page_url=doc.page_url,
                        section_path=doc.section_path,
                        title=doc.title,
                        issue_date=doc.issue_date,
                    )
                )
                if end == len(text):
                    break
                start = max(0, end - self.overlap)

        return chunks
