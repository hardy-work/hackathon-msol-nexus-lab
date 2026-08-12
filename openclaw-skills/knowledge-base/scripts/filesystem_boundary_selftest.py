#!/usr/bin/env python3
"""Contract tests for the runtime's read-only corpus boundary."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from filesystem_boundary import BoundaryError, ReadOnlyCorpus
from runtime_engine import KnowledgeRuntime


def main() -> int:
    old_state = os.environ.get("KNOWLEDGE_BASE_STATE_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="pk-boundary-") as temp:
            root = Path(temp) / "skill"
            root.mkdir()
            (root / "access.yml").write_text(
                "default_visibility: internal\nvisibility_roles:\n  internal: [project_member]\n",
                encoding="utf-8",
            )
            outside = Path(temp) / "outside.txt"
            outside.write_text("must never be readable", encoding="utf-8")
            corpus = ReadOnlyCorpus(root)

            try:
                corpus.resolve("../outside.txt")
            except BoundaryError:
                pass
            else:
                raise AssertionError("path traversal escaped the corpus boundary")

            (root / "wiki").mkdir()
            try:
                (root / "wiki" / "escape.md").symlink_to(outside)
            except OSError:
                # Windows runners without symlink privileges still exercise the
                # traversal/state checks below.
                symlink_supported = False
            else:
                symlink_supported = True
                try:
                    corpus.assert_safe()
                except BoundaryError:
                    pass
                else:
                    raise AssertionError("symlink escaped the corpus boundary")

            if symlink_supported:
                (root / "wiki" / "escape.md").unlink()
            corpus.assert_safe()

            try:
                corpus.assert_state_separate(root / "raw" / "runtime.sqlite3")
            except BoundaryError:
                pass
            else:
                raise AssertionError("runtime state was allowed inside raw/")

            state = Path(temp) / "runtime-state"
            os.environ["KNOWLEDGE_BASE_STATE_DIR"] = str(state)
            runtime = KnowledgeRuntime(root=root)
            result = runtime.query("nexus", "secret", actor="", roles=[], use_cache=False)
            assert result["status"] == "forbidden"
            assert runtime.root == root.resolve()
            assert state.is_dir()
            assert not (root / "derived").exists()

        print("✓ filesystem boundary self-test: 5/5 qua")
        return 0
    finally:
        if old_state is None:
            os.environ.pop("KNOWLEDGE_BASE_STATE_DIR", None)
        else:
            os.environ["KNOWLEDGE_BASE_STATE_DIR"] = old_state


if __name__ == "__main__":
    raise SystemExit(main())
