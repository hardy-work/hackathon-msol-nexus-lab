#!/usr/bin/env python3
"""Regression tests for selective page actions and retired generated pages."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import yaml

import document_registry
import lint
import reingest


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_md(version: int, people: list[str]) -> str:
    return (
        f"---\nraw_id: nexus-people\ndoc_id: nexus-plan\nversion: {version}\n"
        "kind: rollup\n---\n\n" + "\n".join(people) + "\n"
    )


def facts(version: int, people: list[str]) -> dict:
    return {
        "doc_id": "nexus-plan",
        "version": version,
        "facts": {
            slug: {"label": slug, "task_count": {"value": 1, "unit": "task", "src": "Sprint 1!E6"}}
            for slug in people
        },
    }


def person_page(slug: str) -> str:
    return (
        "---\npage: entity-person\nname: \"%s\"\nassignee: %s\nproject: nexus\n"
        "visibility: internal\ntask_count: {facts_ref: \"raw/nexus-people.facts.json#%s.task_count\"}\n"
        "raw_paths:\n  - raw/nexus-people.md\n---\n\n# %s\n\n[[nexus-plan]]\n"
    ) % (slug, slug, slug, slug)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pk-reingest-") as temp:
        root = Path(temp)
        (root / "originals").mkdir()
        (root / "raw").mkdir()
        (root / "wiki/sources").mkdir(parents=True)
        (root / "wiki/entities").mkdir(parents=True)

        old_original, new_original = b"v1", b"v2"
        (root / "originals/nexus-plan.xlsx").write_bytes(old_original)
        (root / "originals/nexus-plan@v2.xlsx").write_bytes(new_original)
        (root / "raw/nexus-people.md").write_text(raw_md(1, ["alice", "bob"]), encoding="utf-8")
        (root / "raw/nexus-people.facts.json").write_text(
            json.dumps(facts(1, ["alice", "bob"])), encoding="utf-8")
        (root / "raw/nexus-people@v2.md").write_text(raw_md(2, ["alice", "carol"]), encoding="utf-8")
        (root / "raw/nexus-people@v2.facts.json").write_text(
            json.dumps(facts(2, ["alice", "carol"])), encoding="utf-8")

        registry = {"documents": [
            {"doc_id": "nexus-plan", "version": 1, "original": "originals/nexus-plan.xlsx",
             "sha256": digest(old_original), "current": False, "supersedes": None,
             "raw_paths": ["raw/nexus-people.md"]},
            {"doc_id": "nexus-plan", "version": 2, "original": "originals/nexus-plan@v2.xlsx",
             "sha256": digest(new_original), "current": True, "supersedes": 1,
             "raw_paths": ["raw/nexus-people@v2.md"]},
        ]}
        (root / "documents.yml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
        (root / "wiki/sources/nexus-plan.md").write_text(
            "---\npage: source\nname: Nexus\ndoc_id: nexus-plan\nversion: 1\n"
            "domain: nexus\nvisibility: internal\nraw_paths: [raw/nexus-people.md]\n---\n\n"
            "[[alice]] [[bob]]\n", encoding="utf-8")
        for slug in ("alice", "bob"):
            (root / f"wiki/entities/{slug}.md").write_text(person_page(slug), encoding="utf-8")
        (root / "wiki/entities/other-domain.md").write_text(
            "---\npage: entity-person\nname: Other\nproject: other\n"
            "visibility: internal\nraw_paths: [raw/nexus-people.md]\n---\n\n# Other\n",
            encoding="utf-8")

        plan = reingest.build_plan(root, "nexus-plan", 1, 2)
        assert plan["new_pages"] == ["wiki/entities/carol.md"]
        assert plan["removed_pages"] == ["wiki/entities/bob.md"]
        assert plan["page_actions"]["write"] == [
            "wiki/entities/alice.md", "wiki/entities/carol.md", "wiki/sources/nexus-plan.md"
        ]
        assert plan["page_actions"]["archive"] == ["wiki/entities/bob.md"]

        reingest.archive_retired_pages(root, plan)
        reingest.archive_one_to_one_pages(root, plan)
        assert (root / "wiki/entities/bob@v1.md").is_file()
        retired = (root / "wiki/entities/bob@v1.md").read_text(encoding="utf-8")
        assert "retired: true" in retired
        assert "retired_by: wiki/sources/nexus-plan.md" in retired
        assert (root / "wiki/sources/nexus-plan@v1.md").is_file()
        assert not (root / "wiki/entities/bob.md").exists()
        assert not (root / "wiki/sources/nexus-plan.md").exists()
        (root / "wiki/sources/nexus-plan.md").write_text(
            "---\npage: source\nname: Nexus\ndoc_id: nexus-plan\nversion: 2\n"
            "domain: nexus\nvisibility: internal\nraw_paths: [raw/nexus-people@v2.md]\n---\n\n"
            "[[alice]] [[carol]]\n", encoding="utf-8")
        (root / "wiki/entities/carol.md").write_text(person_page("carol"), encoding="utf-8")
        lint.errors.clear()
        lint.lint_history(root)
        assert not lint.errors, lint.errors
        document_registry.load(root)

    with tempfile.TemporaryDirectory(prefix="pk-reingest-renderer-change-") as temp:
        root = Path(temp)
        (root / "originals").mkdir()
        (root / "raw").mkdir()
        (root / "wiki/sources").mkdir(parents=True)
        old_original = root / "originals/rules.pdf"
        new_original = root / "originals/rules@v2.md"
        old_original.write_bytes(b"old-pdf")
        new_original.write_bytes(b"new-markdown")
        (root / "raw/rules.md").write_text(
            "---\ndoc_id: rules\nversion: 1\n---\nold\n", encoding="utf-8"
        )
        (root / "raw/rules@v2.md").write_text(
            "---\ndoc_id: rules\nversion: 2\n---\nnew\n", encoding="utf-8"
        )
        registry = {"documents": [
            {"doc_id": "rules", "version": 1, "original": "originals/rules.pdf",
             "kind": "pdf", "extractor": "van", "sha256": digest(b"old-pdf"),
             "current": False, "supersedes": None, "raw_paths": ["raw/rules.md"]},
            {"doc_id": "rules", "version": 2, "original": "originals/rules@v2.md",
             "kind": "text/markdown", "extractor": "markdown",
             "sha256": digest(b"new-markdown"), "current": True, "supersedes": 1,
             "raw_paths": ["raw/rules@v2.md"]},
        ]}
        (root / "documents.yml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
        )
        for name in ("rules.md", "rules--chapter.md"):
            (root / "wiki/sources" / name).write_text(
                "---\npage: source\nname: Rules\ndoc_id: rules\nversion: 1\n"
                "raw_paths: [raw/rules.md]\n---\nold\n", encoding="utf-8"
            )

        plan = reingest.build_plan(root, "rules", 1, 2)
        assert plan["removed_pages"] == ["wiki/sources/rules--chapter.md"]
        assert [item["page"] for item in plan["impacted_pages"]] == [
            "wiki/sources/rules.md"
        ]
        reingest.archive_retired_pages(root, plan)
        reingest.archive_one_to_one_pages(root, plan)
        (root / "wiki/sources/rules.md").write_text(
            "---\npage: source\nname: Rules\ndoc_id: rules\nversion: 2\n"
            "raw_paths: [raw/rules@v2.md]\n---\nnew\n", encoding="utf-8"
        )
        lint.errors.clear()
        lint.lint_history(root)
        assert not lint.errors, lint.errors

    print("✓ re-ingest self-test: selective page write-set + new/retired pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
