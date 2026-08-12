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
    if kind == "facts":
        markdown = [Path(rel) for rel in (document.get("raw_paths") or [])
                    if _identity(rel) == raw_id.casefold() and _kind(rel) == "md"]
        if len(markdown) > 1:
            raise ValueError(f"raw_paths khai trùng artifact `{raw_id}` (md)")
        if markdown:
            return markdown[0].with_suffix(".facts.json")
    version = int(document["version"])
    suffix = {"facts": ".facts.json", "fulltext": ".fulltext.md"}.get(kind, f".{kind}")
    filename = raw_id if version == 1 else f"{raw_id}@v{version}"
    return Path("raw") / f"{filename}{suffix}"


def artifact_path(root: Path, document: dict, raw_id: str, kind: str) -> Path:
    return root / artifact_rel(document, raw_id, kind)


def current_versions(root: Path) -> dict[str, int]:
    return document_registry.current_versions(root)


def relative_path(root: Path, path: str | Path) -> str | None:
    """Return a safe root-relative path for raw artifact ownership checks."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def is_current_raw_path(root: Path, path: str | Path, doc_id: str | None = None) -> bool:
    """Whether a raw path is explicitly retained by a current registry version."""
    rel = relative_path(root, path)
    if not rel:
        return False
    for document in document_registry.load(root):
        if not document.get("current"):
            continue
        if doc_id and str(document.get("doc_id")) != str(doc_id):
            continue
        if _document_declares_path(document, rel):
            return True
        # documents.yml historically declares the Markdown raw path while the
        # paired facts JSON is resolved by artifact_rel(). Treat that implicit
        # facts path as current when its Markdown sibling is retained.
    return False


def _document_declares_path(document: dict, rel: str) -> bool:
    declared = {str(item) for item in document.get("raw_paths") or []}
    if rel in declared:
        return True
    if rel.endswith(".facts.json"):
        markdown = rel[:-len(".facts.json")] + ".md"
        return markdown in declared
    return False


def payload_is_current(payload: dict, root: Path,
                       versions: dict[str, int] | None = None,
                       path: str | Path | None = None) -> bool:
    """Whether a raw JSON payload belongs to a registered current document.

    Missing identity is rejected: facts without ``doc_id``/``version`` cannot
    participate in the evidence-first current corpus.
    """
    doc_id = payload.get("doc_id")
    version = payload.get("version")
    if not doc_id or version is None:
        return False
    versions = versions if versions is not None else current_versions(root)
    if path is not None:
        rel = relative_path(root, path)
        if not rel or not is_current_raw_path(root, rel, str(doc_id)):
            return False
        try:
            registered = document_registry.by_version(str(doc_id), int(version), root)
        except (KeyError, TypeError, ValueError):
            return False
        return _document_declares_path(registered, rel)
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
