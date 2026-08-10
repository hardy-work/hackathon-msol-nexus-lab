#!/usr/bin/env python3
"""Offline self-test for the new-hire training generator."""
from __future__ import annotations

import tempfile
import sys
from pathlib import Path

import create_training
import evaluate_training

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    kb = root.parent / "project-knowledge"
    pages = create_training.discover_pages(kb)
    assert pages, "expected published wiki pages"
    assert all(page.visibility in create_training.ALLOWED_VISIBILITY for page in pages)
    internal, project, team = create_training.classify_pages(pages, "nexus")
    assert internal, "expected internal policy source"
    assert project, "expected project source"
    assert team, "expected team entity source"
    freshness = create_training.check_freshness(kb)
    assert freshness["state"] in {"fresh", "stale", "unknown"}
    registry = create_training.load_document_registry(kb)
    profiles, aliases = create_training.load_role_profiles()
    assert create_training.DEFAULT_ROLES_CONFIG.is_file(), "role profile config missing"
    with tempfile.TemporaryDirectory() as restricted_tmp:
        restricted_root = Path(restricted_tmp)
        (restricted_root / "wiki" / "sources").mkdir(parents=True)
        (restricted_root / "wiki" / "sources" / "restricted.md").write_text(
            "---\npage: source\nname: secret\ndoc_id: secret\nvisibility: restricted\n---\n# secret\n",
            encoding="utf-8",
        )
        assert not create_training.discover_pages(restricted_root), "restricted source leaked"
    text = create_training.render_handbook("nexus", "developer", "Test learner", pages, internal, project, team, freshness, registry, profiles, aliases)
    for marker in ("Mục tiêu sau khi hoàn thành", "Checklist onboarding", "Ma trận nguồn", "Freshness KB", "doc_id=", "Chưa có trong KB"):
        assert marker in text, marker
    assert "doc_id=unknown" not in text, "entity citations should resolve through raw_paths"
    pm_text = create_training.render_handbook("nexus", "project-manager", "Test PM", pages, internal, project, team, freshness, registry, profiles, aliases)
    assert text != pm_text, "role profiles must change the learning path"
    assert "Trọng tâm Developer" in text
    assert "Trọng tâm PM" in pm_text
    assert "**Coverage:** `partial`" in text
    altered = pm_text.replace("Nội quy lao động MOR", "POLICY-CHANGED", 1)
    scoped = create_training.reuse_fixed_policy_modules(text, altered)
    assert "POLICY-CHANGED" not in scoped, "project refresh must retain fixed policy blocks"
    assert "Nội quy lao động MOR" in scoped
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "training.md"
        assert create_training.main(["--kb-root", str(kb), "--project", "nexus", "--role", "developer", "--name", "Test learner", "--output", str(output)]) == 0
        generated = output.read_text(encoding="utf-8")
        assert generated.startswith("# Handbook onboarding")
        assert "noi-quy-lao-dong" in generated
        assert "nexus-plan.md" in generated
        report = evaluate_training.evaluate_artifact(output)
        assert report["pass"], report
    print(f"✓ new-hire-training self-test: {len(pages)} nguồn, internal={len(internal)}, project={len(project)}, team={len(team)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
