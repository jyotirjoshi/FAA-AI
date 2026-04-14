import json
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import date
from pathlib import Path

import httpx

from src.config import settings
from src.models import SectionDocument

ECFR_BASE = "https://www.ecfr.gov"
VERSIONS_URL = f"{ECFR_BASE}/api/versioner/v1/versions/title-14.json"
FULL_URL_TMPL = f"{ECFR_BASE}/api/versioner/v1/full/{{issue_date}}/title-14.xml?part=25"
STRUCTURE_URL_TMPL = f"{ECFR_BASE}/api/versioner/v1/structure/{{issue_date}}/title-14.json"
FULL_PART_URL_TMPL = f"{ECFR_BASE}/api/versioner/v1/full/{{issue_date}}/title-14.xml?part={{part}}"


def _strip_tag(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _iter_text(elem: ET.Element) -> str:
    text = " ".join(t.strip() for t in elem.itertext() if t and t.strip())
    return re.sub(r"\s+", " ", text).strip()


def discover_part25_issue_dates(limit: int = 12) -> list[str]:
    with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        resp = client.get(VERSIONS_URL)
        resp.raise_for_status()
        payload = resp.json()

    versions = payload.get("content_versions", [])
    dates: list[str] = []
    for item in versions:
        if str(item.get("part")) == "25":
            issue_date = item.get("issue_date")
            if issue_date:
                dates.append(issue_date)

    # Keep unique dates in descending order.
    unique_dates = sorted(set(dates), reverse=True)
    if not unique_dates:
        return [date.today().isoformat()]

    # limit <= 0 means keep all available snapshots.
    if limit <= 0:
        return unique_dates

    # Sample across timeline so we keep both recent and historical snapshots.
    if len(unique_dates) <= limit:
        return unique_dates

    step = max(1, len(unique_dates) // limit)
    sampled = unique_dates[::step][: limit - 1]
    if unique_dates[-1] not in sampled:
        sampled.append(unique_dates[-1])
    return sampled


def latest_issue_date_title14() -> str:
    with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        resp = client.get(VERSIONS_URL)
        resp.raise_for_status()
        payload = resp.json()

    versions = payload.get("content_versions", [])
    issue_dates = [v.get("issue_date") for v in versions if v.get("issue_date")]
    if not issue_dates:
        return date.today().isoformat()
    return max(issue_dates)


def discover_title14_issue_dates(limit: int = 3) -> list[str]:
    with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        resp = client.get(VERSIONS_URL)
        resp.raise_for_status()
        payload = resp.json()

    versions = payload.get("content_versions", [])
    dates = [v.get("issue_date") for v in versions if v.get("issue_date")]
    unique_dates = sorted(set(dates), reverse=True)
    if not unique_dates:
        return [date.today().isoformat()]

    if limit <= 0 or len(unique_dates) <= limit:
        return unique_dates

    sampled = unique_dates[:limit]
    # Always keep the oldest available snapshot in the sample for historical comparison.
    oldest = unique_dates[-1]
    if oldest not in sampled:
        sampled[-1] = oldest
    return list(dict.fromkeys(sampled))


def fetch_title14_parts(issue_date: str) -> list[str]:
    url = STRUCTURE_URL_TMPL.format(issue_date=issue_date)
    with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()

    parts: set[str] = set()

    def walk(node: dict) -> None:
        node_type = str(node.get("type", "")).lower()
        identifier = str(node.get("identifier", "")).strip()
        if node_type == "part" and identifier:
            parts.add(identifier)
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                walk(child)

    if isinstance(payload, dict):
        walk(payload)

    def part_sort_key(p: str) -> tuple[int, str]:
        m = re.match(r"^(\d+)", p)
        if m:
            return (int(m.group(1)), p)
        return (10**9, p)

    return sorted(parts, key=part_sort_key)


def parse_part25_xml(xml_text: str, issue_date: str, source_id: str, source_url: str) -> list[SectionDocument]:
    docs: list[SectionDocument] = []
    root = ET.fromstring(xml_text)

    for elem in root.iter():
        tag = _strip_tag(elem.tag).upper()
        elem_type = str(elem.attrib.get("TYPE", "")).upper()
        if not ((tag == "DIV8" and elem_type == "SECTION") or tag == "SECTION"):
            continue

        sectno = str(elem.attrib.get("N", "")).strip()
        subject = ""
        for child in list(elem):
            child_tag = _strip_tag(child.tag).upper()
            if child_tag == "SECTNO":
                sectno = _iter_text(child)
            elif child_tag in {"SUBJECT", "HEAD", "HD2"} and not subject:
                subject = _iter_text(child)

        body_text = _iter_text(elem)
        if len(body_text) < 120:
            continue

        title = f"{sectno} {subject}".strip() or f"Part 25 Section ({issue_date})"
        section_path = f"eCFR Part 25 ({issue_date}) > {sectno}".strip()
        page_url = FULL_URL_TMPL.format(issue_date=issue_date)

        docs.append(
            SectionDocument(
                source_id=source_id,
                source_url=source_url,
                page_url=page_url,
                section_path=section_path,
                title=title,
                content=body_text,
                issue_date=issue_date,
            )
        )

    return docs


def parse_ecfr_part_xml(
    xml_text: str,
    issue_date: str,
    part: str,
    source_id: str,
    source_url: str,
) -> list[SectionDocument]:
    docs: list[SectionDocument] = []
    root = ET.fromstring(xml_text)

    for elem in root.iter():
        tag = _strip_tag(elem.tag).upper()
        elem_type = str(elem.attrib.get("TYPE", "")).upper()
        if not ((tag == "DIV8" and elem_type == "SECTION") or tag == "SECTION"):
            continue

        sectno = str(elem.attrib.get("N", "")).strip()
        subject = ""
        for child in list(elem):
            child_tag = _strip_tag(child.tag).upper()
            if child_tag == "SECTNO":
                sectno = _iter_text(child)
            elif child_tag in {"SUBJECT", "HEAD", "HD2"} and not subject:
                subject = _iter_text(child)

        body_text = _iter_text(elem)
        if len(body_text) < 120:
            continue

        title = f"{sectno} {subject}".strip() or f"Part {part} Section ({issue_date})"
        section_path = f"eCFR Title 14 Part {part} ({issue_date}) > {sectno}".strip()
        page_url = FULL_PART_URL_TMPL.format(issue_date=issue_date, part=part)

        docs.append(
            SectionDocument(
                source_id=source_id,
                source_url=source_url,
                page_url=page_url,
                section_path=section_path,
                title=title,
                content=body_text,
                issue_date=issue_date,
            )
        )

    return docs


def ingest_ecfr_part25(raw_dir: Path, source: dict, history_limit: int = 10) -> list[SectionDocument]:
    source_id = source["id"]
    source_url = source["url"]

    out_file = raw_dir / f"{source_id}.jsonl"
    raw_dir.mkdir(parents=True, exist_ok=True)

    dates = discover_part25_issue_dates(limit=history_limit)
    # Preserve order and ensure at least the most recent issue date is first.
    dates = list(OrderedDict.fromkeys(dates))
    print(f"[ecfr:part25] dates={len(dates)}")

    all_docs: list[SectionDocument] = []
    with httpx.Client(timeout=60, follow_redirects=True) as client, out_file.open("w", encoding="utf-8") as f:
        for idx, issue_date in enumerate(dates, start=1):
            url = FULL_URL_TMPL.format(issue_date=issue_date)
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                docs = parse_part25_xml(resp.text, issue_date=issue_date, source_id=source_id, source_url=source_url)
            except Exception:
                continue

            all_docs.extend(docs)
            for d in docs:
                f.write(json.dumps(d.__dict__, ensure_ascii=False) + "\n")
            print(f"[ecfr:part25] processed_dates={idx}/{len(dates)} docs={len(all_docs)}")

    return all_docs


def ingest_ecfr_title14_full(
    raw_dir: Path,
    source: dict,
    max_parts: int | None = None,
    history_limit: int = 1,
) -> list[SectionDocument]:
    source_id = source["id"]
    source_url = source["url"]

    out_file = raw_dir / f"{source_id}.jsonl"
    raw_dir.mkdir(parents=True, exist_ok=True)

    issue_dates = discover_title14_issue_dates(limit=history_limit)
    print(f"[ecfr:title14] issue_dates={issue_dates}")

    parts = fetch_title14_parts(issue_dates[0])
    if max_parts is not None and max_parts > 0:
        parts = parts[:max_parts]

    all_docs: list[SectionDocument] = []
    with httpx.Client(timeout=90, follow_redirects=True) as client, out_file.open("w", encoding="utf-8") as f:
        for issue_date in issue_dates:
            print(f"[ecfr:title14] processing issue_date={issue_date} parts={len(parts)}")
            for idx, part in enumerate(parts, start=1):
                url = FULL_PART_URL_TMPL.format(issue_date=issue_date, part=part)
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue
                    docs = parse_ecfr_part_xml(
                        xml_text=resp.text,
                        issue_date=issue_date,
                        part=part,
                        source_id=source_id,
                        source_url=source_url,
                    )
                except Exception:
                    continue

                all_docs.extend(docs)
                for d in docs:
                    f.write(json.dumps(d.__dict__, ensure_ascii=False) + "\n")

                if idx % 10 == 0:
                    print(f"[ecfr:title14] processed issue_date={issue_date} parts={idx}/{len(parts)} docs={len(all_docs)}")

    print(f"[ecfr:title14] done docs={len(all_docs)} file={out_file}")
    return all_docs
