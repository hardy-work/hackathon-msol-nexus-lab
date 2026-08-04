#!/usr/bin/env python3
"""CI fixture for intake -> re-ingest -> Gate 3a -> derive.

The fixture copies the canonical skill to a temporary staging root, changes one
workbook cell, registers it as v2, and runs the same executor used by a real
ingest worktree.  It never modifies the repository's canonical originals/wiki.
"""
from __future__ import annotations

import shutil
import os
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


def main() -> int:
    os.environ.setdefault("PROJECT_KNOWLEDGE_EMBEDDING_BACKEND", "hash")
    with tempfile.TemporaryDirectory(prefix="pk-ingest-flow-") as temp:
        temp_root = Path(temp)
        staging = temp_root / "project-knowledge"

        def ignore(_path: str, names: list[str]) -> set[str]:
            return {name for name in names if name in {"derived", ".runtime", "__pycache__"}}

        shutil.copytree(ROOT, staging, ignore=ignore)
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
        assert '"archived_page": "wiki/sources/nexus-plan@v1.md"' in plan.read_text(encoding="utf-8")
        assert (staging / "derived/facts.duckdb").is_file()
        assert (staging / "derived/graph.json").is_file()
        assert (staging / "derived/rag_indexes.json").is_file()
        assert not __import__("rag_index").required_errors(staging)

    print("✓ ingest-flow self-test: intake → re-ingest v2 → Gate 3a → derive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
