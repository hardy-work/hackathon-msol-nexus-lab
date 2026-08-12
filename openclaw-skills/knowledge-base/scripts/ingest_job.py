#!/usr/bin/env python3
"""Persistent background job wrapper for Slack-triggered ingest.

``start`` returns immediately so the transport can acknowledge Slack.  The
detached worker owns the deterministic ingest + publish commands and writes a
small status/completion artifact for the gateway to deliver to the thread.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_proposal  # noqa: E402
import ingest_publisher  # noqa: E402
import ingest_runner  # noqa: E402
import runtime_state  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "knowledge-base/ingest-job/v1"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _directory(root: Path) -> Path:
    return runtime_state.state_dir(root) / "ingest-jobs"


def _path(proposal_id: str, root: Path) -> Path:
    return _directory(root) / f"{proposal_id}.json"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def load(proposal_id: str, root: Path = ROOT) -> dict[str, Any]:
    try:
        payload = json.loads(_path(proposal_id, root).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"không tìm thấy ingest job cho {proposal_id}") from exc
    if payload.get("schema") != SCHEMA:
        raise ValueError("ingest job sai schema")
    return payload


def _save(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    _atomic_json(_path(str(payload["proposal_id"]), root), payload)
    return payload


def _completion(proposal: dict[str, Any]) -> dict[str, Any]:
    execution = proposal.get("execution") or {}
    source = proposal.get("source") or {}
    requester = proposal.get("requested_by") or {}
    slack = proposal.get("slack_context") or {}
    return {
        "schema": "knowledge-base/ingest-completion/v1",
        "proposal_id": proposal.get("proposal_id"),
        "status": proposal.get("status"),
        "source_name": source.get("name"),
        "requester": requester,
        "channel_id": slack.get("channel_id") or proposal.get("channel_id"),
        "thread_ts": slack.get("thread_ts") or proposal.get("thread_ts"),
        "corpus_version": execution.get("corpus_version"),
        "runtime_reloaded": execution.get("runtime_reloaded", False),
    }


def worker(proposal_id: str, *, root: Path = ROOT,
           full_regression: bool = False) -> dict[str, Any]:
    job = load(proposal_id, root)
    job.update({"status": "running", "stage": "ingest", "started_at": _now()})
    _save(job, root)
    try:
        ingest_runner.run(
            proposal_id, run_all=full_regression, root=root
        )
        job.update({"stage": "publish", "updated_at": _now()})
        _save(job, root)
        proposal = ingest_publisher.publish(proposal_id, root=root)
        job.update({
            "status": "completed", "stage": "published", "finished_at": _now(),
            "completion": _completion(proposal),
        })
    except Exception as exc:
        try:
            proposal = ingest_proposal.load(proposal_id, root)
            completion = _completion(proposal)
        except Exception:
            completion = {"proposal_id": proposal_id, "status": "failed"}
        job.update({
            "status": "failed", "stage": job.get("stage"), "finished_at": _now(),
            "error": f"{type(exc).__name__}: {exc}", "completion": completion,
        })
        _save(job, root)
        raise
    return _save(job, root)


def start(proposal_id: str, *, root: Path = ROOT,
          full_regression: bool = False) -> dict[str, Any]:
    proposal = ingest_proposal.load(proposal_id, root)
    if proposal.get("status") != "ready_to_ingest":
        raise ValueError(
            f"chỉ ready_to_ingest mới được start, hiện là {proposal.get('status')}"
        )
    path = _path(proposal_id, root)
    if path.exists():
        previous = load(proposal_id, root)
        if previous.get("status") in {"queued", "running"}:
            return previous
    log_path = _directory(root) / f"{proposal_id}.log"
    job = {
        "schema": SCHEMA,
        "proposal_id": proposal_id,
        "status": "queued",
        "stage": "queued",
        "created_at": _now(),
        "log_path": str(log_path),
        "full_regression": bool(full_regression),
    }
    _save(job, root)
    command = [
        sys.executable, str(Path(__file__).resolve()), "worker", proposal_id,
        "--root", str(root.resolve()),
    ]
    if full_regression:
        command.append("--full-regression")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True,
            cwd=Path(__file__).resolve().parent.parent,
            env=os.environ.copy(),
        )
    job["pid"] = process.pid
    job["accepted_at"] = _now()
    return _save(job, root)


def submit(source: Path, *, actor: str, requester_name: str = "",
           channel_id: str = "", thread_ts: str = "", message_ts: str = "",
           message_permalink: str = "", confirmed_doc_id: str | None = None,
           root: Path = ROOT, full_regression: bool = False) -> dict[str, Any]:
    """Create an authorized proposal and enqueue it in one transport call."""
    proposal = ingest_proposal.create(
        source, actor=actor, requester_name=requester_name,
        channel_id=channel_id, thread_ts=thread_ts, message_ts=message_ts,
        message_permalink=message_permalink,
        confirmed_doc_id=confirmed_doc_id, root=root,
    )
    if proposal.get("status") != "ready_to_ingest":
        return {
            "accepted": False,
            "proposal_id": proposal["proposal_id"],
            "proposal_status": proposal.get("status"),
            "requires_identity": proposal.get("status") == "awaiting_identity",
            "proposal": proposal,
        }
    job = start(
        str(proposal["proposal_id"]), root=root,
        full_regression=full_regression,
    )
    return {
        "accepted": True,
        "proposal_id": proposal["proposal_id"],
        "proposal_status": proposal.get("status"),
        "job_status": job.get("status"),
        "job": job,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Background knowledge ingest job")
    sub = parser.add_subparsers(dest="command", required=True)
    submit_parser = sub.add_parser("submit")
    submit_parser.add_argument("--file", required=True, type=Path)
    submit_parser.add_argument("--actor", required=True)
    submit_parser.add_argument("--name", default="")
    submit_parser.add_argument("--channel-id", default="")
    submit_parser.add_argument("--thread-ts", default="")
    submit_parser.add_argument("--message-ts", default="")
    submit_parser.add_argument("--message-permalink", default="")
    submit_parser.add_argument("--doc-id")
    submit_parser.add_argument("--root", type=Path, default=ROOT)
    submit_parser.add_argument("--full-regression", action="store_true")
    for name in ("start", "worker"):
        command = sub.add_parser(name)
        command.add_argument("proposal_id")
        command.add_argument("--root", type=Path, default=ROOT)
        command.add_argument("--full-regression", action="store_true")
    status = sub.add_parser("status")
    status.add_argument("proposal_id")
    status.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        if args.command == "submit":
            result = submit(
                args.file, actor=args.actor, requester_name=args.name,
                channel_id=args.channel_id, thread_ts=args.thread_ts,
                message_ts=args.message_ts,
                message_permalink=args.message_permalink,
                confirmed_doc_id=args.doc_id, root=args.root,
                full_regression=args.full_regression,
            )
        elif args.command == "start":
            result = start(
                args.proposal_id, root=args.root,
                full_regression=args.full_regression,
            )
        elif args.command == "worker":
            result = worker(
                args.proposal_id, root=args.root,
                full_regression=args.full_regression,
            )
        else:
            result = load(args.proposal_id, args.root)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError,
            json.JSONDecodeError, ingest_proposal.ProposalError) as exc:
        print(f"✗ ingest job: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
