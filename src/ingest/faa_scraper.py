import json
from io import BytesIO
import re
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.config import settings
from src.models import SectionDocument

HEADER_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_SUFFIXES = {
    ".pdf",
    ".zip",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}


def normalize_url(url: str) -> str:
    url, _fragment = urldefrag(url)
    parsed = urlparse(url)
    return parsed._replace(query=parsed.query, fragment="").geturl()


def is_allowed(url: str, allow_prefixes: list[str]) -> bool:
    return any(url.startswith(prefix) for prefix in allow_prefixes)


def has_allowed_scope(url: str, include_substrings: list[str] | None) -> bool:
    if not include_substrings:
        return True
    return any(s in url for s in include_substrings)


def is_skippable_link(url: str) -> bool:
    lower = url.lower()
    return any(lower.endswith(suffix) for suffix in SKIP_SUFFIXES)


def is_pdf_url(url: str) -> bool:
    return url.lower().endswith(".pdf")


def extract_pdf_docs(
    pdf_bytes: bytes,
    page_url: str,
    source_id: str,
    source_url: str,
) -> list[SectionDocument]:
    docs: list[SectionDocument] = []
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        for idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if len(text) < 80:
                continue
            docs.append(
                SectionDocument(
                    source_id=source_id,
                    source_url=source_url,
                    page_url=f"{page_url}#page={idx}",
                    section_path=f"PDF Page {idx}",
                    title=f"PDF Page {idx}",
                    content=text,
                )
            )
    except Exception:
        return []
    return docs


def extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


def split_sections(html: str, page_url: str, source_id: str, source_url: str) -> list[SectionDocument]:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup
    title = (soup.title.string.strip() if soup.title and soup.title.string else page_url)

    docs: list[SectionDocument] = []
    headings_stack: list[str] = [title]
    current_lines: list[str] = []

    def flush(section_title: str) -> None:
        text = "\n".join(line for line in current_lines if line.strip()).strip()
        if len(text) < 120:
            return
        docs.append(
            SectionDocument(
                source_id=source_id,
                source_url=source_url,
                page_url=page_url,
                section_path=" > ".join(headings_stack),
                title=section_title,
                content=text,
            )
        )

    current_section_title = title
    for node in body.descendants:
        if getattr(node, "name", None) in HEADER_TAGS:
            flush(current_section_title)
            level = int(node.name[1])
            heading_text = node.get_text(" ", strip=True)
            if not heading_text:
                continue
            headings_stack = headings_stack[:level]
            headings_stack.append(heading_text)
            current_section_title = heading_text
            current_lines = []
            continue

        if getattr(node, "name", None) in {"p", "li", "td", "th"}:
            line = node.get_text(" ", strip=True)
            line = re.sub(r"\s+", " ", line)
            if line:
                current_lines.append(line)

    flush(current_section_title)

    if not docs:
        text = extract_main_text(html)
        if text:
            docs.append(
                SectionDocument(
                    source_id=source_id,
                    source_url=source_url,
                    page_url=page_url,
                    section_path=title,
                    title=title,
                    content=text,
                )
            )

    return docs


def extract_links(
    html: str,
    base_url: str,
    allow_prefixes: list[str],
    include_substrings: list[str] | None,
    allow_pdf: bool,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        abs_url = normalize_url(urljoin(base_url, a["href"]))
        if is_skippable_link(abs_url) and not (allow_pdf and is_pdf_url(abs_url)):
            continue
        if is_allowed(abs_url, allow_prefixes) and has_allowed_scope(abs_url, include_substrings):
            links.append(abs_url)
    return links


def fetch_html(client: httpx.Client, url: str, retries: int = 3) -> str | None:
    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            resp = client.get(url)
            if resp.status_code != 200:
                continue
            content_type = (resp.headers.get("content-type") or "").lower()
            if "text/html" not in content_type:
                return None
            return resp.text
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc:
        return None
    return None


def crawl_source(source: dict, raw_dir: Path) -> list[SectionDocument]:
    source_id = source["id"]
    start_url = source["url"]
    allow_prefixes = source["allow_prefixes"]
    include_substrings = source.get("include_substrings")
    allow_pdf = bool(source.get("allow_pdf", False))
    source_max = int(source.get("max_pages", settings.max_pages_per_source))
    max_pages = min(source_max, int(settings.max_pages_per_source))

    queue = deque([normalize_url(start_url)])
    seen: set[str] = set()
    all_docs: list[SectionDocument] = []
    out_file = raw_dir / f"{source_id}.jsonl"

    print(f"[crawl:{source_id}] start={start_url}")
    print(f"[crawl:{source_id}] max_pages={max_pages}")

    with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        raw_dir.mkdir(parents=True, exist_ok=True)
        with out_file.open("w", encoding="utf-8") as f:
            while queue and len(seen) < max_pages:
                url = queue.popleft()
                if url in seen:
                    continue
                seen.add(url)

                html = fetch_html(client, url)
                if not html:
                    if allow_pdf and is_pdf_url(url):
                        try:
                            pdf_resp = client.get(url)
                            if pdf_resp.status_code == 200:
                                pdf_docs = extract_pdf_docs(
                                    pdf_bytes=pdf_resp.content,
                                    page_url=url,
                                    source_id=source_id,
                                    source_url=start_url,
                                )
                                all_docs.extend(pdf_docs)
                                for d in pdf_docs:
                                    f.write(json.dumps(d.__dict__, ensure_ascii=False) + "\n")
                        except Exception:
                            pass

                    if len(seen) % 25 == 0:
                        print(f"[crawl:{source_id}] visited={len(seen)} queued={len(queue)} docs={len(all_docs)}")
                    continue

                docs = split_sections(html=html, page_url=url, source_id=source_id, source_url=start_url)
                all_docs.extend(docs)
                for d in docs:
                    f.write(json.dumps(d.__dict__, ensure_ascii=False) + "\n")

                for link in extract_links(
                    html,
                    base_url=url,
                    allow_prefixes=allow_prefixes,
                    include_substrings=include_substrings,
                    allow_pdf=allow_pdf,
                ):
                    if link not in seen:
                        queue.append(link)

                if len(seen) % 25 == 0:
                    print(f"[crawl:{source_id}] visited={len(seen)} queued={len(queue)} docs={len(all_docs)}")

    print(f"[crawl:{source_id}] done visited={len(seen)} docs={len(all_docs)} file={out_file}")

    return all_docs
