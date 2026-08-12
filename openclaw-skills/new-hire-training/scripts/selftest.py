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
    kb = root.parent / "knowledge-base"
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
    for marker in ("Mục tiêu sau khi hoàn thành", "Checklist onboarding", "Ma trận nguồn", "Freshness KB", "Nguồn:", "Chưa có trong KB"):
        assert marker in text, marker
    assert "Nguồn:" in text, "training must render reader-facing source provenance"
    source_lines = [line for line in text.splitlines() if "Nguồn:" in line]
    assert all("wiki/" not in line and "raw/" not in line for line in source_lines), "internal paths must not be shown in citations"
    pm_text = create_training.render_handbook("nexus", "project-manager", "Test PM", pages, internal, project, team, freshness, registry, profiles, aliases)
    assert text != pm_text, "role profiles must change the learning path"
    assert "Trọng tâm Developer" in text
    assert "Trọng tâm PM" in pm_text
    assert "**Coverage:** `partial`" in text
    assert "nguồn có thể là OCR" not in text, "current Markdown policy must not be labelled as OCR"
    policy_title = next(page.title for page in internal if page.doc_id.startswith("noi-quy-lao-dong-"))
    altered = pm_text.replace(policy_title, "POLICY-CHANGED", 1)
    scoped = create_training.reuse_fixed_policy_modules(text, altered)
    assert "POLICY-CHANGED" not in scoped, "project refresh must retain fixed policy blocks"
    assert policy_title in scoped
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "training.md"
        assert create_training.main(["--kb-root", str(kb), "--project", "nexus", "--role", "developer", "--name", "Test learner", "--output", str(output)]) == 0
        generated = output.read_text(encoding="utf-8")
        assert generated.startswith("# Handbook onboarding")
        assert "1760635210-MOR.BO.PRO.01" in generated
        assert "Nguồn:" in generated
        assert "1760635210-MOR.BO.PRO.01" in generated
        assert "cập nhật ngày 10/08/2026 · bởi MH_DoNT" in generated
        source_lines = [line for line in generated.splitlines() if "Nguồn:" in line]
        assert all("wiki/" not in line and "raw/" not in line for line in source_lines)
        assert "noi-quy-lao-dong-20260808T041339Z-aa1429cc79@v1.md" not in generated, "historical OCR policy pages must not enter training"
        assert "noi-quy-lao-dong-20260808T041339Z-aa1429cc79--chuong-" not in generated, "historical OCR chapter pages must not enter training"
        assert "Các trang OCR có thể" not in generated
        assert "Nexus Plan.xlsx" in generated
        report = evaluate_training.evaluate_artifact(output)
        assert report["pass"], report
    print(f"✓ new-hire-training self-test: {len(pages)} nguồn, internal={len(internal)}, project={len(project)}, team={len(team)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
