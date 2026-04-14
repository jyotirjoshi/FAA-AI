import json
from pathlib import Path

from pypdf import PdfReader

from src.models import SectionDocument


def file_url(path: Path) -> str:
    return path.resolve().as_uri()


def ingest_pdf(pdf_path: Path, source_id: str, source_url: str) -> list[SectionDocument]:
    reader = PdfReader(str(pdf_path))
    docs: list[SectionDocument] = []

    for page_idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.strip()
        if len(text) < 80:
            continue
        docs.append(
            SectionDocument(
                source_id=source_id,
                source_url=source_url,
                page_url=f"{source_url}#page={page_idx}",
                section_path=f"PDF Page {page_idx}",
                title=f"PDF Page {page_idx}",
                content=text,
            )
        )

    return docs


def save_pdf_docs(docs: list[SectionDocument], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d.__dict__, ensure_ascii=False) + "\n")
