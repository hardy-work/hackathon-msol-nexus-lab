#!/usr/bin/env python3
"""Execute an authorized ingest proposal in an isolated worktree.

The runner is the bridge between the Slack-facing allowlist and the existing
``ingest_flow.py``. It stops at ``ready_to_publish`` after fast release-blocking
gates and a content-addressed manifest. ``ingest_publisher.py`` then owns the
single deterministic merge/promote/record transition.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_flow  # noqa: E402
import ingest_proposal  # noqa: E402
import intake  # noqa: E402
import publish_gates  # noqa: E402
import review_artifact  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def run(proposal_id: str, *, base: str = "main", run_all: bool = False,
        root: Path = ROOT
        ) -> dict:
    proposal = ingest_proposal.load(proposal_id, root)
    if proposal["status"] != "ready_to_ingest":
        raise ingest_proposal.ProposalError(
            f"chỉ proposal ready_to_ingest mới được chạy, hiện là {proposal['status']}")
    ingest_proposal._assert_source_unchanged(proposal)
    if not proposal.get("review_artifact"):
        artifact = review_artifact.build(
            Path(proposal["source"]["path"]), proposal_id=proposal_id)
        output = ingest_proposal._proposal_dir(root) / proposal_id / "review"
        bundle = review_artifact.write_bundle(artifact, output)
        proposal = ingest_proposal.attach_review_artifact(proposal_id, bundle, root=root)
    decision = proposal.get("intake_decision") or {}
    if decision.get("flow") not in {"initial_ingest", "reingest"}:
        raise ingest_proposal.ProposalError(
            f"intake flow `{decision.get('flow')}` chưa sẵn sàng chạy")
    doc_id = str(decision["doc_id"])
    version = int(decision.get("version") or decision.get("to_version"))
    source = Path(proposal["source"]["path"])
    requester = proposal.get("requested_by") or {}
    decision = dict(decision)
    decision.setdefault("updated_at", _now().split("T", 1)[0])
    decision.setdefault("updated_by", requester.get("name") or requester.get("user_id") or "NexusBot (hệ thống)")
    proposal["intake_decision"] = decision
    started = _now()
    proposal["status"] = "running"
    proposal["execution"] = {"status": "running", "started_at": started,
                              "base": base, "doc_id": doc_id, "version": version}
    proposal["events"].append({"type": "ingest_started", "at": started,
                                "proposal_id": proposal_id})
    ingest_proposal.save(proposal, root)
    branch = None
    worktree = None
    base_commit = None
    validation = None
    try:
        base_commit = subprocess.check_output(
            [ingest_flow.git_executable(), "rev-parse", base],
            cwd=ingest_flow.REPO, text=True,
        ).strip()
        branch, worktree = ingest_flow.prepare(doc_id, version, base)
        target = ingest_flow.skill_root(worktree)
        registered = intake.register(target, source, decision)
        # execute() runs the extractor, selective re-ingest, Gate 3a, Gate 3b,
        # DuckDB/graph/RAG derive and corpus freshness build in the worktree.
        ingest_flow.execute(worktree, doc_id, version, review=True)
        if run_all:
            # Full code/demo regression is opt-in. Production data ingest uses
            # publish_gates below, which validates the exact artifacts that
            # will be promoted without rebuilding them a second time.
            run_all_env = os.environ.copy()
            # Keep the interpreter selected by the host runner.  Otherwise a
            # launchd service may fall back to macOS system Python even though
            # the runner itself is using the project virtualenv.
            run_all_env.setdefault("KNOWLEDGE_BASE_PYTHON", sys.executable)
            subprocess.run(["bash", "scripts/run_all.sh"], cwd=target,
                           env=run_all_env, check=True)
        artifact_json = None
        review_bundle = proposal.get("review_artifact") or {}
        if review_bundle.get("json_path"):
            artifact_json = Path(str(review_bundle["json_path"]))
        validation = publish_gates.run(
            target, proposal_id=proposal_id, doc_id=doc_id, version=version,
            review_artifact_path=artifact_json, git_commit=base_commit,
        )
    except Exception as exc:
        proposal = ingest_proposal.load(proposal_id, root)
        proposal["status"] = "failed"
        proposal["execution"] = {
            "status": "failed", "started_at": started, "failed_at": _now(),
            "base": base, "branch": branch, "worktree": str(worktree) if worktree else None,
            "error": f"{type(exc).__name__}: {exc}",
        }
        proposal["events"].append({"type": "ingest_failed", "at": _now(),
                                    "error": proposal["execution"]["error"]})
        ingest_proposal.save(proposal, root)
        raise

    proposal = ingest_proposal.load(proposal_id, root)
    proposal["status"] = "ready_to_publish"
    proposal["execution"] = {
        "status": "gates_passed", "started_at": started, "finished_at": _now(),
        "base": base, "branch": branch, "worktree": str(worktree),
        "base_commit": base_commit,
        "registered": registered,
        "validation": validation,
        "publish_required": True,
        "runtime_reload_required": True,
    }
    proposal["events"].append({"type": "gates_passed", "at": _now(),
                                "branch": branch, "worktree": str(worktree)})
    return ingest_proposal.save(proposal, root)


def record_published(proposal_id: str, *, corpus_version: str,
                     runtime_reloaded: bool, root: Path = ROOT) -> dict:
    proposal = ingest_proposal.load(proposal_id, root)
    if proposal["status"] != "ready_to_publish":
        raise ingest_proposal.ProposalError(
            f"chỉ ready_to_publish mới được record-published, hiện là {proposal['status']}")
    if not corpus_version.strip():
        raise ingest_proposal.ProposalError("thiếu corpus_version")
    if not runtime_reloaded:
        raise ingest_proposal.ProposalError(
            "chưa xác nhận reload runtime; không ghi proposal là published")
    now = _now()
    proposal["status"] = "published"
    proposal["published_at"] = now
    proposal["execution"].update({
        "status": "published", "corpus_version": corpus_version,
        "runtime_reloaded": True, "published_at": now,
    })
    proposal["events"].append({"type": "published", "at": now,
                                "corpus_version": corpus_version,
                                "runtime_reloaded": True})
    return ingest_proposal.save(proposal, root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run/record an authorized ingest proposal")
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("proposal_id")
    run_parser.add_argument("--base", default="main")
    run_parser.add_argument("--full-regression", action="store_true",
                            help="opt-in: chạy full run_all.sh ngoài publish gates")
    run_parser.add_argument("--skip-run-all", action="store_true",
                            help=argparse.SUPPRESS)
    publish_parser = sub.add_parser("record-published")
    publish_parser.add_argument("proposal_id")
    publish_parser.add_argument("--corpus-version", required=True)
    publish_parser.add_argument("--runtime-reloaded", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            result = run(args.proposal_id, base=args.base,
                         run_all=args.full_regression and not args.skip_run_all,
                         root=args.root.resolve())
        else:
            result = record_published(
                args.proposal_id, corpus_version=args.corpus_version,
                runtime_reloaded=args.runtime_reloaded, root=args.root.resolve())
    except (OSError, RuntimeError, ValueError, KeyError, ingest_proposal.ProposalError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
