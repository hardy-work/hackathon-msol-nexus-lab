#!/usr/bin/env python3
"""Evaluate generated onboarding artifacts without calling an LLM."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


REQUIRED_HEADINGS = (
    "## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.",
)


def _normalise_body(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("# Handbook onboarding —"):
            line = "# Handbook onboarding — ROLE"
        if line.startswith("- **Vai trò:**"):
            line = "- **Vai trò:** ROLE"
        if line.startswith("- **Snapshot KB:**"):
            line = "- **Snapshot KB:** DATE"
        if line.startswith("- **Regeneration scope:**"):
            line = "- **Regeneration scope:** SCOPE"
        lines.append(line)
    return "\n".join(lines)


def evaluate_artifact(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    modules = re.findall(r"(?m)^### 2\.\d+ (.+)$", text)
    scopes = re.findall(r"(?m)^- \*\*Scope:\*\* `([^`]+)`$", text)
    coverage = re.findall(r"(?m)^- \*\*Coverage:\*\* `([^`]+)`$", text)
    source_lines = [line for line in text.splitlines() if "Nguồn:" in line]
    citations = len(source_lines)
    unknown_citations = sum("Nguồn: `chưa xác định`" in line for line in source_lines)
    raw_path_citations = sum("wiki/" in line or "raw/" in line for line in source_lines)
    missing_markers = text.count("[Chưa có trong KB]")
    checks = {
        "required_sections": all(marker in text for marker in REQUIRED_HEADINGS),
        "role_profile": "Hồ sơ đào tạo" in text and "role_guidance" in scopes,
        "fixed_policy_scope": scopes.count("policy_fixed") >= 2,
        "dynamic_project_scope": scopes.count("project_dynamic") >= 2,
        "source_citations": citations > 0 and unknown_citations == 0 and raw_path_citations == 0,
        "freshness": "Freshness KB" in text,
        "explicit_gaps": missing_markers > 0 and "partial" in coverage,
    }
    score = round(100 * sum(checks.values()) / len(checks))
    return {
        "artifact": str(path),
        "pass": all(checks.values()),
        "score": score,
        "modules": len(modules),
        "module_titles": modules,
        "scope_counts": {scope: scopes.count(scope) for scope in sorted(set(scopes))},
        "coverage_counts": {item: coverage.count(item) for item in sorted(set(coverage))},
        "citations": citations,
        "unknown_citations": unknown_citations,
        "raw_path_citations": raw_path_citations,
        "missing_markers": missing_markers,
        "checks": checks,
    }


def evaluate_directory(directory: Path) -> dict[str, object]:
    artifacts = sorted(directory.glob("*.md"))
    results = [evaluate_artifact(path) for path in artifacts]
    normalised = {_normalise_body(path.read_text(encoding="utf-8")) for path in artifacts}
    return {
        "directory": str(directory),
        "artifacts": results,
        "artifact_count": len(results),
        "unique_role_bodies": len(normalised),
        "pass": bool(results) and all(bool(item["pass"]) for item in results),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--artifact", type=Path)
    group.add_argument("--dir", dest="directory", type=Path)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)
    report = (evaluate_artifact(args.artifact) if args.artifact
              else evaluate_directory(args.directory))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.artifact:
        print(f"TRAINING EVAL  {args.artifact.name}: score={report['score']} pass={report['pass']}")
        print(f"  modules={report['modules']} citations={report['citations']} unknown={report['unknown_citations']} gaps={report['missing_markers']}")
        for name, passed in report["checks"].items():
            print(f"  {'✓' if passed else '✗'} {name}")
    else:
        print(f"TRAINING EVAL  {report['artifact_count']} artifacts pass={report['pass']}")
        print(f"  unique_role_bodies={report['unique_role_bodies']}")
        for item in report["artifacts"]:
            print(f"  {'✓' if item['pass'] else '✗'} {Path(item['artifact']).name}: score={item['score']} modules={item['modules']} unknown={item['unknown_citations']}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
