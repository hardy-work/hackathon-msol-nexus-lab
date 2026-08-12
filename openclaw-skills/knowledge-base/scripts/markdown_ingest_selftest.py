#!/usr/bin/env python3
"""CI fixture for Markdown intake -> raw -> wiki source -> derived indexes."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import document_registry  # noqa: E402
import ingest_flow  # noqa: E402
import intake  # noqa: E402
import markdown_source  # noqa: E402


SOURCE = """**Chính sách an toàn thông tin**

Nhân viên phải sử dụng mật khẩu có ít nhất 8 ký tự.
Tài liệu được lưu nguyên văn để truy xuất cùng provenance.
"""


def main() -> int:
    os.environ.setdefault("KNOWLEDGE_BASE_EMBEDDING_BACKEND", "hash")
    with tempfile.TemporaryDirectory(prefix="pk-markdown-ingest-") as temp:
        temp_root = Path(temp)
        staging = temp_root / "knowledge-base"

        def ignore(_path: str, names: list[str]) -> set[str]:
            return {name for name in names if name in {"derived", ".runtime", "__pycache__"}}

        shutil.copytree(ROOT, staging, ignore=ignore)
        incoming = temp_root / "chinh-sach-an-toan-thong-tin.md"
        incoming.write_text(SOURCE, encoding="utf-8")
        original_bytes = incoming.read_bytes()

        decision = intake.decide(staging, incoming)
        assert decision["flow"] == "initial_ingest", decision
        assert decision["kind"] == "text/markdown"
        assert decision["content_metadata"] == {
            "title": "Chính sách an toàn thông tin",
            "domain": "mor-software",
            "lang": "vi",
            "domain_source": "access.ingest.default_domain",
        }
        registered = intake.register(staging, incoming, decision)
        doc_id = decision["doc_id"]
        document = document_registry.current(doc_id, staging)
        assert document["extractor"] == "markdown"
        assert document["raw_paths"] == [f"raw/{doc_id}.md"]
        assert document["domain"] == "mor-software"
        assert document["title"] == "Chính sách an toàn thông tin"
        assert registered["registered_original"].endswith(f"{doc_id}.md")
        registered_original = staging / registered["registered_original"]
        assert registered_original.read_bytes() == original_bytes
        assert not registered_original.read_text(encoding="utf-8").startswith("---\n")

        os.environ["KNOWLEDGE_BASE_STATE_DIR"] = str(temp_root / "runtime")
        ingest_flow.execute(staging, doc_id, 1, review=False)

        raw = staging / f"raw/{doc_id}.md"
        page = staging / f"wiki/sources/{doc_id}.md"
        assert raw.is_file()
        assert page.is_file()
        raw_metadata, raw_body = markdown_source.parse(raw)
        assert raw_metadata["domain"] == "mor-software"
        assert raw_metadata["title"] == "Chính sách an toàn thông tin"
        assert raw_body == SOURCE
        page_text = page.read_text(encoding="utf-8")
        assert "domain: mor-software" in page_text
        assert f"- raw/{doc_id}.md" in page_text
        page_metadata, page_body = markdown_source.parse(page)
        assert page_metadata["name"] == "Chính sách an toàn thông tin"
        assert page_body == SOURCE
        assert (staging / "derived/facts.duckdb").is_file()
        assert (staging / "derived/graph.json").is_file()
        assert (staging / "derived/rag_indexes.json").is_file()

        incoming_v2 = temp_root / "chinh-sach-an-toan-thong-tin-v2.md"
        incoming_v2.write_text(SOURCE.replace("ít nhất 8", "ít nhất 12"),
                               encoding="utf-8")
        decision_v2 = intake.decide(staging, incoming_v2, confirmed_doc_id=doc_id)
        assert decision_v2["flow"] == "reingest", decision_v2
        assert decision_v2["from_version"] == 1
        assert decision_v2["to_version"] == 2
        assert decision_v2["content_metadata"]["domain"] == "mor-software"
        assert decision_v2["content_metadata"]["domain_source"] == "registry"
        intake.register(staging, incoming_v2, decision_v2)
        ingest_flow.execute(staging, doc_id, 2, review=False)

        current = document_registry.current(doc_id, staging)
        assert int(current["version"]) == 2
        assert current["raw_paths"] == [f"raw/{doc_id}@v2.md"]
        assert (staging / f"raw/{doc_id}@v2.md").is_file()
        history = staging / f"wiki/sources/{doc_id}@v1.md"
        assert history.is_file()
        assert f"superseded_by: wiki/sources/{doc_id}.md" in history.read_text(encoding="utf-8")

        explicit = temp_root / "nexus-note.md"
        explicit.write_text(
            "---\ntitle: Nexus note\ndomain: nexus\nlang: en\n---\n# Nexus note\n",
            encoding="utf-8",
        )
        explicit_decision = intake.decide(staging, explicit)
        assert explicit_decision["content_metadata"]["domain"] == "nexus"
        assert explicit_decision["content_metadata"]["domain_source"] == "frontmatter.domain"

        invalid = temp_root / "unknown-domain.md"
        invalid.write_text("---\ndomain: external\n---\n# Unknown\n", encoding="utf-8")
        try:
            intake.decide(staging, invalid)
        except ValueError as exc:
            assert "chưa được curate" in str(exc)
        else:
            raise AssertionError("Markdown khai domain lạ phải fail closed ở intake")

    with tempfile.TemporaryDirectory(prefix="pk-markdown-conversion-") as temp:
        temp_root = Path(temp)
        (temp_root / "originals").mkdir()
        (temp_root / "raw").mkdir()
        shutil.copy2(ROOT / "schema.yml", temp_root / "schema.yml")
        shutil.copy2(ROOT / "access.yml", temp_root / "access.yml")
        old_original = temp_root / "originals/employee-rules.pdf"
        old_original.write_bytes(b"old-pdf-placeholder")
        registry = f"""documents:
  - doc_id: employee-rules
    version: 1
    original: originals/employee-rules.pdf
    source_name: employee-rules.pdf
    kind: pdf
    sha256: {intake.sha256(old_original)}
    status: canonical
    current: true
    supersedes: null
    visibility: internal
    extractor: van
    raw_paths:
      - raw/employee-rules.md
"""
        (temp_root / "documents.yml").write_text(registry, encoding="utf-8")
        incoming = temp_root / "uploads/employee-rules.md"
        incoming.parent.mkdir()
        incoming.write_text(SOURCE, encoding="utf-8")

        decision = intake.decide(
            temp_root, incoming, confirmed_doc_id="employee-rules"
        )
        assert decision["flow"] == "reingest", decision
        intake.register(temp_root, incoming, decision)
        current = document_registry.current("employee-rules", temp_root)
        assert current["kind"] == "text/markdown"
        assert current["extractor"] == "markdown"
        assert current["raw_paths"] == ["raw/employee-rules@v2.md"]

    print("✓ Markdown self-test: intake → raw → wiki source → derive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
