#!/usr/bin/env python3
"""Shared parsing rules for Markdown source documents."""
from __future__ import annotations

import re
from pathlib import Path

import yaml


FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def parse(path: Path) -> tuple[dict, str]:
    """Return source frontmatter and body without changing the body bytes."""
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"frontmatter Markdown phải là mapping: {path}")
    return metadata, match.group(2)


def slug(value: str) -> str:
    value = value.casefold().replace("đ", "d")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return re.sub(r"-(?:jsc|ltd|llc|inc|corp|corporation)$", "", value)


def title(metadata: dict, body: str, fallback: str) -> str:
    if metadata.get("title"):
        return str(metadata["title"])
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    # Documents copied from rich-text systems commonly use a bold first line
    # instead of a Markdown H1.  Treat only a whole-line strong heading as a
    # title; do not guess from arbitrary prose.
    for line in body.splitlines():
        value = line.strip()
        match = re.fullmatch(r"\*\*(.+?)\*\*", value)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return fallback


def domain(metadata: dict, fallback: str = "") -> str:
    """Resolve explicit metadata first, then a trusted curated fallback."""
    if metadata.get("domain"):
        return str(metadata["domain"])
    if metadata.get("org"):
        value = slug(str(metadata["org"]))
        if value:
            return value
    if str(fallback or "").strip():
        return str(fallback).strip()
    raise ValueError("Markdown source thiếu `domain` hoặc `org` trong frontmatter")
