#!/usr/bin/env python3
"""CI fixture for intake -> re-ingest -> Gate 3a -> derive.

The fixture copies the canonical skill to a temporary staging root, changes one
workbook cell, registers it as v2, and runs the same executor used by a real
ingest worktree.  It never modifies the repository's canonical originals/wiki.
"""
from __future__ import annotations

import shutil
import os
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import document_registry  # noqa: E402
import ingest_flow  # noqa: E402
import intake  # noqa: E402


def assert_changed_wiki_pages_are_scoped(temp_root: Path) -> None:
    """Initial ingest review must exclude unchanged index/source pages."""
    repo = temp_root / "review-repo"
    skill = repo / "openclaw-skills/knowledge-base"
    (skill / "wiki/entities").mkdir(parents=True)
    (skill / "wiki/sources").mkdir(parents=True)
    (skill / "wiki/index.md").write_text("index\n", encoding="utf-8")
    (skill / "wiki/log.md").write_text("log\n", encoding="utf-8")
    (skill / "wiki/sources/old.md").write_text("old\n", encoding="utf-8")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run([
        "git", "-C", str(repo), "-c", "user.name=fixture",
        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "base",
    ], check=True)

    (skill / "wiki/sources/old.md").write_text("updated\n", encoding="utf-8")
    (skill / "wiki/entities/new.md").write_text("new\n", encoding="utf-8")
    (skill / "wiki/sources/incoming.md").write_text("incoming\n", encoding="utf-8")
    (skill / "wiki/index.md").write_text("updated index\n", encoding="utf-8")
    (repo / "not-wiki.md").write_text("ignore\n", encoding="utf-8")

    assert ingest_flow.changed_wiki_pages(repo, skill) == [
        "wiki/entities/new.md",
        "wiki/sources/incoming.md",
        "wiki/sources/old.md",
    ]


def assert_runtime_copy_resolves_nested_skill(temp_root: Path) -> None:
    """A runtime skill copy must resolve the nested skill inside its worktree."""
    repo = temp_root / "runtime-repo"
    skill = repo / "openclaw-skills/knowledge-base"
    (skill / "scripts").mkdir(parents=True)
    (skill / "documents.yml").write_text("documents: []\n", encoding="utf-8")
    runtime_skill = temp_root / "openclaw-workspace/skills/knowledge-base"
    runtime_skill.mkdir(parents=True)

    original_repo, original_skill = ingest_flow.REPO, ingest_flow.SKILL
    try:
        ingest_flow.REPO = repo
        ingest_flow.SKILL = runtime_skill
        assert ingest_flow.skill_root(repo) == skill
        assert ingest_flow.skill_root(skill) == skill
    finally:
        ingest_flow.REPO, ingest_flow.SKILL = original_repo, original_skill


def main() -> int:
    os.environ.setdefault("KNOWLEDGE_BASE_EMBEDDING_BACKEND", "hash")
    with tempfile.TemporaryDirectory(prefix="pk-ingest-flow-") as temp:
        temp_root = Path(temp)
        assert_changed_wiki_pages_are_scoped(temp_root)
        assert_runtime_copy_resolves_nested_skill(temp_root)
        staging = temp_root / "knowledge-base"

        def ignore(_path: str, names: list[str]) -> set[str]:
            return {name for name in names if name in {"derived", ".runtime", "__pycache__"}}

        shutil.copytree(ROOT, staging, ignore=ignore)
        entity_before = {
            path.relative_to(staging).as_posix(): path.read_bytes()
            for path in sorted((staging / "wiki/entities").glob("*.md"))
        }
        incoming = temp_root / "Nexus Plan.xlsx"
        shutil.copy2(staging / "originals/nexus-plan.xlsx", incoming)
        workbook = openpyxl.load_workbook(incoming)
        workbook["Summary project"]["K4"] = "CI re-ingest fixture"
        workbook.save(incoming)
        workbook.close()

        decision = intake.decide(staging, incoming, confirmed_doc_id="nexus-plan")
        assert decision["flow"] == "reingest", decision
        assert decision["from_version"] == 1
        assert decision["to_version"] == 2
        intake.register(staging, incoming, decision)

        ingest_flow.execute(staging, "nexus-plan", 2, review=False)

        current = document_registry.current("nexus-plan", staging)
        assert int(current["version"]) == 2
        assert "raw/nexus-summary@v2.md" in current["raw_paths"]
        assert "raw/nexus-people.md" in current["raw_paths"]
        assert not (staging / "raw/nexus-people@v2.md").exists()
        assert not (staging / "raw/nexus-people@v2.facts.json").exists()
        for rel, before in entity_before.items():
            assert (staging / rel).read_bytes() == before, rel
        current_page = staging / "wiki/sources/nexus-plan.md"
        assert current_page.is_file()
        current_text = current_page.read_text(encoding="utf-8")
        assert "`originals/nexus-plan@v2.xlsx`" in current_text
        assert "originals/nexus-plan.xlsx" not in current_text
        archived = staging / "wiki/sources/nexus-plan@v1.md"
        assert archived.is_file()
        assert "superseded_by: wiki/sources/nexus-plan.md" in archived.read_text(encoding="utf-8")
        plan = staging / "derived/reingest-plan.json"
        assert plan.is_file()
        plan_data = json.loads(plan.read_text(encoding="utf-8"))
        assert plan_data["page_actions"]["write"] == ["wiki/sources/nexus-plan.md"]
        assert plan_data["new_pages"] == []
        assert plan_data["removed_pages"] == []
        changed_raw_ids = {row["artifact"].split("::", 1)[0] for row in plan_data["raw_diff"]}
        assert "nexus-summary" in changed_raw_ids
        assert not changed_raw_ids & {"nexus-config", "nexus-sprint1", "nexus-people"}
        assert '"archived_page": "wiki/sources/nexus-plan@v1.md"' in plan.read_text(encoding="utf-8")
        assert (staging / "derived/facts.duckdb").is_file()
        assert (staging / "derived/graph.json").is_file()
        assert (staging / "derived/rag_indexes.json").is_file()
        assert not __import__("rag_index").required_errors(staging)

    print("✓ ingest-flow self-test: intake → re-ingest v2 → Gate 3a → derive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
