#!/usr/bin/env python3
"""Deterministic completeness checks for prose wiki pages.

Numeric/provenance gates prove that claims which a model wrote are grounded.  This
module checks the other direction: every numbered Điều/khoản in the supplied source
scope is represented in the generated page, or is explicitly marked as not covered.
It deliberately does not use an LLM and therefore adds no ingest tokens.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numeric_guard


_ARTICLE_RE = re.compile(
    r"^\s*#{0,6}\s*(?:Điều)\s+(\d{1,3})(?=\D|$)", re.IGNORECASE
)
_CLAUSE_RE = re.compile(
    r"^\s*#{0,6}\s*(?:[-*]\s*)?(?:>\s*)?(?:\*\*)?"
    r"(\d{1,3}(?:\.\d{1,3})+)(?:\*\*)?(?=\s|[.),:;—–-]|$)"
)
_INLINE_CLAUSE_RE = re.compile(
    r"\b(?:mục|khoản)\s+(\d{1,3}(?:\.\d{1,3})+)", re.IGNORECASE
)
_MARKED_RE = re.compile(
    r"(?:\[\s*(?:chưa\s+bao\s+phủ|not\s+covered|không\s+có\s+trong\s+trích\s+đoạn)"
    r"\s*:\s*|<!--\s*NOT_COVERED\s*:\s*)(\d{1,3}(?:\.\d{1,3})+)",
    re.IGNORECASE,
)


def _normalise_identifier(value: str) -> str:
    value = value.strip().rstrip(".")
    parts = value.split(".")
    if len(parts) < 1 or not all(part.isdigit() for part in parts):
        return ""
    if not all(1 <= len(part) <= 3 for part in parts):
        return ""
    return ".".join(str(int(part)) for part in parts)


def extract_identifiers(text: str) -> set[str]:
    """Extract only line-leading article/clause identifiers.

    Restricting matches to line starts avoids treating prose references such as
    ``xem Điều 35`` or dates in a paragraph as coverage for a missing clause.
    """
    found: set[str] = set()
    scoped = _content_scope(text)
    for line in scoped.splitlines():
        article = _ARTICLE_RE.match(line)
        if article:
            identifier = _normalise_identifier(article.group(1))
            if identifier:
                found.add(identifier)
            continue
        clause = _CLAUSE_RE.match(line)
        if clause:
            identifier = _normalise_identifier(clause.group(1))
            if identifier:
                found.add(identifier)
    for match in _INLINE_CLAUSE_RE.finditer(scoped):
        identifier = _normalise_identifier(match.group(1))
        if identifier:
            found.add(identifier)
    return found


def _content_scope(text: str) -> str:
    """Remove document control/TOC material before extracting source IDs.

    Chapter 1 contains the full table of contents before its actual ``Điều 1``
    body, and every chapter can repeat page headers such as ``Lần ban hành: 1.0``.
    Neither is source coverage for that chapter.
    """
    lines = str(text or "").splitlines()
    toc_start = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*#{0,6}\s*MỤC\s*LỤC\s*$", line, re.IGNORECASE):
            toc_start = index
            break
    if toc_start is not None:
        toc_end = None
        for index in range(toc_start + 1, len(lines)):
            if re.match(r"^\s*\[\[page\s+\d+\]\]\s*$", lines[index], re.IGNORECASE):
                toc_end = index
                break
        if toc_end is not None:
            lines = lines[:toc_start] + lines[toc_end:]
        else:
            lines = lines[:toc_start]
    # Start at the first article that is followed by one of its own clauses.
    # The OCR structure sometimes renders the first article as plain text, and
    # chapter 1 contains a plain-text TOC before the real ``Điều 1`` body.  A
    # matching ``Điều N`` + ``N.1`` pair distinguishes body from TOC without
    # relying on page numbers or a model.
    first_article = None
    article_candidates = []
    for index, line in enumerate(lines):
        article = _ARTICLE_RE.match(line)
        if article:
            article_candidates.append((index, _normalise_identifier(article.group(1))))
    for index, identifier in article_candidates:
        if not identifier:
            continue
        for following in lines[index + 1:index + 10]:
            clause = _CLAUSE_RE.match(following)
            if clause and _normalise_identifier(clause.group(1)).startswith(identifier + "."):
                first_article = index
                break
        if first_article is not None:
            break
    if first_article is None and article_candidates:
        first_article = article_candidates[0][0]
    if first_article is not None:
        lines = lines[first_article:]
    return "\n".join(lines)


def extract_marked(text: str) -> set[str]:
    """Extract explicit ``[Chưa bao phủ: 33.1]`` markers from a page."""
    return {
        identifier
        for raw in _MARKED_RE.findall(str(text or ""))
        if (identifier := _normalise_identifier(raw))
    }


def _body_only(page_text: str) -> str:
    try:
        _, body = numeric_guard.split_frontmatter(page_text)
    except (TypeError, ValueError):
        body = str(page_text or "")
    # Source/citation footer is navigation metadata, not page coverage.
    body = re.split(r"(?im)^\s*#{1,6}\s*Nguồn\s*$", body, maxsplit=1)[0]
    return body


def check(source_scope: str, page_text: str) -> dict[str, object]:
    """Return an auditable coverage report for one source scope/page pair."""
    expected = extract_identifiers(source_scope)
    body = _body_only(page_text)
    actual = extract_identifiers(body)
    marked = extract_marked(body)
    missing = expected - actual - marked
    unexpected = actual - expected
    marked_unexpected = marked - expected
    return {
        "status": "pass" if not missing and not unexpected and not marked_unexpected else "fail",
        "complete": not missing and not marked,
        "expected": sorted(expected, key=_sort_key),
        "covered": sorted(actual & expected, key=_sort_key),
        "marked_not_covered": sorted(marked & expected, key=_sort_key),
        "missing": sorted(missing, key=_sort_key),
        "unexpected": sorted(unexpected, key=_sort_key),
        "marked_unexpected": sorted(marked_unexpected, key=_sort_key),
    }


def _sort_key(identifier: str) -> tuple[int, ...]:
    return tuple(int(part) for part in identifier.split("."))


def format_problems(report: dict[str, object]) -> list[str]:
    """Turn a report into concise gate errors while retaining the JSON report."""
    problems: list[str] = []
    missing = report.get("missing") or []
    unexpected = report.get("unexpected") or []
    marked_unexpected = report.get("marked_unexpected") or []
    if missing:
        problems.append("thiếu Điều/khoản: " + ", ".join(missing))
    if unexpected:
        problems.append("Điều/khoản ngoài source scope: " + ", ".join(unexpected))
    if marked_unexpected:
        problems.append("marker không thuộc source scope: " + ", ".join(marked_unexpected))
    return problems


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


__all__ = [
    "check", "extract_identifiers", "extract_marked", "format_problems", "write_report",
]
