"""Resolve versioned raw artifacts and reject superseded facts.

The document registry owns the current version and its ``raw_paths``.  All
derived readers use this module so a re-ingest can keep old raw artifacts for
diff/review without allowing them into the current corpus.
"""
from __future__ import annotations

import re
from pathlib import Path

import document_registry


VERSION_SUFFIX = re.compile(r"(?:[@._-](?:v|version)\d+)$", re.IGNORECASE)


def _identity(path: str | Path) -> str:
    name = Path(path).name
    if name.endswith(".facts.json"):
        name = name[: -len(".facts.json")]
    elif name.endswith(".fulltext.md"):
        name = name[: -len(".fulltext.md")]
    else:
        name = Path(name).stem
    return VERSION_SUFFIX.sub("", name).casefold()


def _kind(path: str | Path) -> str:
    name = Path(path).name
    if name.endswith(".facts.json"):
        return "facts"
    if name.endswith(".fulltext.md"):
        return "fulltext"
    return Path(name).suffix.lower().lstrip(".")


def artifact_rel(document: dict, raw_id: str, kind: str) -> Path:
    """Return the declared path for one artifact, with a safe version fallback.

    Version 1 keeps the existing canonical filenames.  Later versions default
    to ``@vN`` so callers cannot accidentally overwrite an immutable artifact;
    an explicitly declared path in ``documents.yml`` always wins.
    """
    candidates = [
        Path(rel) for rel in (document.get("raw_paths") or [])
        if _identity(rel) == raw_id.casefold() and _kind(rel) == kind
    ]
    if len(candidates) > 1:
        raise ValueError(f"raw_paths khai trùng artifact `{raw_id}` ({kind})")
    if candidates:
        return candidates[0]
    version = int(document["version"])
    suffix = {"facts": ".facts.json", "fulltext": ".fulltext.md"}.get(kind, f".{kind}")
    filename = raw_id if version == 1 else f"{raw_id}@v{version}"
    return Path("raw") / f"{filename}{suffix}"


def artifact_path(root: Path, document: dict, raw_id: str, kind: str) -> Path:
    return root / artifact_rel(document, raw_id, kind)


def current_versions(root: Path) -> dict[str, int]:
    return document_registry.current_versions(root)


def payload_is_current(payload: dict, root: Path, versions: dict[str, int] | None = None) -> bool:
    """Whether a raw JSON payload belongs to a registered current document.

    Missing identity is rejected: facts without ``doc_id``/``version`` cannot
    participate in the evidence-first current corpus.
    """
    doc_id = payload.get("doc_id")
    version = payload.get("version")
    if not doc_id or version is None:
        return False
    versions = versions if versions is not None else current_versions(root)
    try:
        return int(version) == int(versions[str(doc_id)])
    except (KeyError, TypeError, ValueError):
        return False


def frontmatter_is_current(metadata: dict, root: Path,
                           versions: dict[str, int] | None = None) -> bool:
    """Check versioned page metadata; unversioned entity pages remain valid."""
    if not metadata.get("doc_id") or metadata.get("version") is None:
        return True
    versions = versions if versions is not None else current_versions(root)
    try:
        return int(metadata["version"]) == int(versions[str(metadata["doc_id"])])
    except (KeyError, TypeError, ValueError):
        return False
