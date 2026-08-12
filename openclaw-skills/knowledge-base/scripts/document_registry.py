#!/usr/bin/env python3
"""Human-owned document identity/version registry helpers."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(root: Path = ROOT) -> list[dict[str, Any]]:
    path = root / "documents.yml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    docs = payload.get("documents") or []
    seen = set()
    currents = {}
    for doc in docs:
        key = (str(doc.get("doc_id")), int(doc.get("version", 0)))
        if not key[0] or key[1] <= 0 or key in seen:
            raise ValueError(f"documents.yml có định danh/version không hợp lệ hoặc trùng: {key}")
        seen.add(key)
        if doc.get("current"):
            if key[0] in currents:
                raise ValueError(f"doc_id {key[0]} có nhiều version current")
            currents[key[0]] = key[1]
        original = root / str(doc.get("original", ""))
        if not original.exists():
            raise ValueError(f"original không tồn tại: {doc.get('original')}")
        actual = sha256(original)
        if actual != doc.get("sha256"):
            raise ValueError(f"sha256 registry lệch: {doc.get('original')}")
        supersedes = doc.get("supersedes")
        if supersedes is not None and int(supersedes) >= key[1]:
            raise ValueError(f"{key[0]}@v{key[1]} supersedes phải nhỏ hơn version hiện tại")
    for doc in docs:
        supersedes = doc.get("supersedes")
        if supersedes is not None and (str(doc["doc_id"]), int(supersedes)) not in seen:
            raise ValueError(
                f"{doc['doc_id']}@v{doc['version']} supersedes version không tồn tại: {supersedes}"
            )
    return docs


def write(root: Path, documents: list[dict[str, Any]]) -> None:
    """Persist the human-owned registry while retaining its introductory comments."""
    path = root / "documents.yml"
    original = path.read_text(encoding="utf-8")
    prefix_lines = []
    for line in original.splitlines(keepends=True):
        if line.strip() == "documents:":
            break
        prefix_lines.append(line)
    rendered = yaml.safe_dump(
        {"documents": documents}, allow_unicode=True, sort_keys=False
    )
    path.write_text("".join(prefix_lines) + rendered, encoding="utf-8")


def current(doc_id: str, root: Path = ROOT) -> dict[str, Any]:
    matches = [doc for doc in load(root) if doc.get("doc_id") == doc_id and doc.get("current")]
    if len(matches) != 1:
        raise KeyError(f"không có đúng một version current cho {doc_id}")
    return matches[0]


def by_version(doc_id: str, version: int, root: Path = ROOT) -> dict[str, Any]:
    for doc in load(root):
        if doc.get("doc_id") == doc_id and int(doc.get("version")) == int(version):
            return doc
    raise KeyError(f"không tìm thấy version {doc_id}@v{version} trong documents.yml")


def require_version_1(doc_id: str, root: Path = ROOT) -> dict[str, Any]:
    """Require a registered v1 before any update can enter re-ingest."""
    try:
        return by_version(doc_id, 1, root)
    except KeyError as exc:
        raise ValueError(
            f"không thể re-ingest {doc_id}: documents.yml chưa có version 1; "
            "hãy đưa tài liệu qua initial ingest trước"
        ) from exc


def classify_intake(doc_id: str, root: Path = ROOT) -> dict[str, Any]:
    """Choose initial-ingest, re-ingest, or fail closed for an incoming document."""
    docs = [doc for doc in load(root) if str(doc.get("doc_id")) == str(doc_id)]
    if not docs:
        return {
            "flow": "initial_ingest",
            "doc_id": doc_id,
            "version": 1,
            "reason": "doc_id chưa có trong documents.yml",
        }

    require_version_1(doc_id, root)
    try:
        current_doc = current(doc_id, root)
    except KeyError as exc:
        raise ValueError(
            f"không thể nhận tài liệu {doc_id}: registry không có đúng một version current"
        ) from exc
    from_version = int(current_doc["version"])
    return {
        "flow": "reingest",
        "doc_id": doc_id,
        "from_version": from_version,
        "to_version": from_version + 1,
        "reason": f"đã có version 1 và current đang là v{from_version}",
    }


def current_versions(root: Path = ROOT) -> dict[str, int]:
    return {str(doc["doc_id"]): int(doc["version"])
            for doc in load(root) if doc.get("current")}


def _citation_base(citation: str) -> tuple[str, str]:
    """Split an internal locator from its human-readable cell/field suffix."""
    value = str(citation or "").strip()
    base = value
    suffix = ""
    for separator in (" :: ", " → ", " ("):
        if separator in base:
            base, suffix = base.split(separator, 1)
            suffix = suffix.rstrip(")").strip()
            break
    base = base.split("#", 1)[0].strip()
    return base, suffix


def _safe_path(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _page_identity(root: Path, relative: str) -> tuple[str, int] | None:
    path = _safe_path(root, relative)
    if path is None or not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[:80]
    except (OSError, UnicodeDecodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    doc_id = version = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^(doc_id|version):\s*['\"]?([^'\"]+)['\"]?\s*$", line)
        if not match:
            continue
        if match.group(1) == "doc_id":
            doc_id = match.group(2).strip()
        else:
            try:
                version = int(match.group(2).strip())
            except ValueError:
                return None
    return (doc_id, version) if doc_id and version else None


def _page_raw_paths(root: Path, relative: str) -> set[str]:
    path = _safe_path(root, relative)
    if path is None or not path.is_file():
        return set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
        metadata = yaml.safe_load("\n".join(lines[1:end])) or {}
    except (OSError, UnicodeDecodeError, StopIteration, yaml.YAMLError):
        return set()
    values = metadata.get("raw_paths") or []
    if isinstance(values, str):
        values = [values]
    return {str(value) for value in values}


def document_for_citation(citation: str, root: Path = ROOT) -> dict[str, Any] | None:
    """Resolve a raw/wiki citation to its registered current document."""
    base, _ = _citation_base(citation)
    if not base:
        return None
    documents = load(root)
    for document in documents:
        if not document.get("current"):
            continue
        declared = {str(item) for item in document.get("raw_paths") or []}
        if base in declared:
            return document
        if base.endswith(".facts.json") and base[:-len(".facts.json")] + ".md" in declared:
            return document
    identity = _page_identity(root, base) if base.startswith("wiki/") else None
    if identity:
        doc_id, version = identity
        return next((doc for doc in documents
                     if str(doc.get("doc_id")) == doc_id
                     and int(doc.get("version", 0)) == version), None)
    if base.startswith("wiki/"):
        page_raw_paths = _page_raw_paths(root, base)
        for document in documents:
            if page_raw_paths & {str(item) for item in document.get("raw_paths") or []}:
                return document
    return None


def _display_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "chưa ghi nhận"
    date = text.split("T", 1)[0]
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date)
    return f"{match.group(3)}/{match.group(2)}/{match.group(1)}" if match else text


def public_citation(citation: str, root: Path = ROOT) -> str:
    """Render provenance for readers without exposing internal wiki paths."""
    base, suffix = _citation_base(citation)
    document = document_for_citation(citation, root)
    if document:
        origin = str(document.get("source_origin") or "").strip()
        source_name = str(document.get("source_name") or
                          Path(str(document.get("original", ""))).name)
        source = f"`{origin or source_name}`"
        rendered = (f"Nguồn: {source} · cập nhật ngày "
                    f"{_display_date(document.get('updated_at'))} · bởi "
                    f"{document.get('updated_by') or 'chưa ghi nhận'}")
    else:
        name = Path(base).name if base else "chưa xác định"
        rendered = f"Nguồn: `{name}` · cập nhật ngày chưa ghi nhận · bởi chưa ghi nhận"
    if suffix:
        rendered += f" · phạm vi {suffix}"
    return rendered


def public_citations(citations: list[str] | tuple[str, ...] | None,
                     root: Path = ROOT) -> list[str]:
    """Map a citation list to deduplicated reader-facing provenance labels."""
    result: list[str] = []
    for citation in citations or []:
        rendered = public_citation(str(citation), root)
        if rendered not in result:
            result.append(rendered)
    return result
