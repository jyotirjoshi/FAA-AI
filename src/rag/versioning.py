from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime


DATE_PATTERNS = [
    re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(19\d{2}|20\d{2})\b"),
]


@dataclass
class QueryVersionHint:
    requested_date: date | None
    is_historical: bool
    is_current: bool
    wants_change_summary: bool


def parse_query_date(query: str) -> date | None:
    text = query.lower()

    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass

    # Common natural-language date hint: "as of 2020" / "in 2018".
    year_match = re.search(r"\b(?:as of|in|effective in|before|after)\s+(19\d{2}|20\d{2})\b", text)
    if year_match:
        return date(int(year_match.group(1)), 12, 31)

    if "historical" in text or "old version" in text or "previous version" in text:
        return date(1900, 1, 1)

    if any(token in text for token in ["current law", "latest law", "now", "today", "current version"]):
        return None

    return None


def build_query_version_hint(query: str) -> QueryVersionHint:
    requested_date = parse_query_date(query)
    text = query.lower()
    wants_change_summary = any(token in text for token in ["what changed", "changes", "difference", "updated", "how did it change", "change over time"])
    return QueryVersionHint(
        requested_date=requested_date,
        is_historical=bool(requested_date and requested_date.year < 2025),
        is_current=any(token in text for token in ["current law", "latest law", "now", "today", "current version"]) or requested_date is None,
        wants_change_summary=wants_change_summary,
    )


def parse_issue_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None