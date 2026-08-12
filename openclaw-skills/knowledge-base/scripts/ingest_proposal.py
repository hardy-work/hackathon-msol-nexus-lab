#!/usr/bin/env python3
"""Authorized proposal state machine for Slack-triggered knowledge ingest.

NexusBot owns Slack transport and calls this module with trusted actor/context
metadata.  The module deliberately does not call Google or publish the corpus:
it creates an auditable proposal and validates the source. There is no human
approval step: the configured Slack user allowlist is the authorization gate.

State is operational data and lives outside the read-only corpus, normally at
``.runtime/ingest-proposals`` or ``KNOWLEDGE_BASE_STATE_DIR``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intake  # noqa: E402
import runtime_state  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "knowledge-base/ingest-proposal/v2"
DEFAULT_INGEST_USERS = {
    "U03H0QB426A": "MH_TungDV",
    "U03Q60UCBJS": "MA_Toan",
    "U03SC6QAP52": "MH_PhongDT",
    "U03TJ5FG3K7": "MH_Duong_MH",
    "U08FT511ZEF": "MH_HoangMV",
    "U08GQJRUT3Q": "MH_KienDT",
    "U09PXK5SCP4": "MH_Ngoc Long",
    "U09QRTUHX24": "MH_SonBH",
    "U0A2PDFHHL7": "MH_VinhNV",
    "U0APQSSGKTM": "MH_DoNT",
}
ALLOWED_KINDS = {
    "xlsx", "docx", "pptx", "pdf", "text/markdown", "text/csv", "csv",
}
ACTIVE_STATES = {"awaiting_identity", "ready_to_ingest", "running"}
TERMINAL_STATES = {"published", "failed", "stale", "no_op", "duplicate"}


class ProposalError(ValueError):
    """A caller-visible proposal or authorization contract violation."""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _access_policy(root: Path) -> dict[str, Any]:
    path = root / "access.yml"
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def ingest_policy(root: Path = ROOT) -> dict[str, Any]:
    """Return the normalized Slack ID allowlist for ingest."""
    configured = _access_policy(root).get("ingest") or {}
    rows = configured.get("allowed_users") or [
        {"user_id": user_id, "name": name}
        for user_id, name in DEFAULT_INGEST_USERS.items()
    ]
    allowed_users = {}
    for row in rows:
        if isinstance(row, dict) and row.get("user_id"):
            allowed_users[str(row["user_id"])] = str(row.get("name") or row["user_id"])
    if not allowed_users:
        allowed_users = dict(DEFAULT_INGEST_USERS)
    return {
        "mode": "slack_user_allowlist",
        "allowed_users": allowed_users,
    }


def _roles(value: str | list[str] | tuple[str, ...] | None) -> set[str]:
    if isinstance(value, str):
        return {part.strip() for part in value.split(",") if part.strip()}
    return {str(part).strip() for part in (value or []) if str(part).strip()}


def authorize_requester(actor: str, roles: str | list[str] | None = None,
                        root: Path = ROOT) -> tuple[bool, str]:
    """Authorize proposal creation from the trusted Slack user ID."""
    actor = str(actor or "").strip()
    if not actor:
        return False, "missing trusted requester Slack user ID"
    policy = ingest_policy(root)
    if actor in policy["allowed_users"]:
        return True, f"Slack user được allowlist: {policy['allowed_users'][actor]}"
    return False, "Slack user không nằm trong allowlist knowledge_base:ingest"


def _proposal_dir(root: Path = ROOT) -> Path:
    return runtime_state.state_dir(root) / "ingest-proposals"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def _path_for(proposal_id: str, root: Path = ROOT) -> Path:
    if not proposal_id or Path(proposal_id).name != proposal_id:
        raise ProposalError("proposal_id không hợp lệ")
    return _proposal_dir(root) / f"{proposal_id}.json"


def load(proposal_id: str, root: Path = ROOT) -> dict[str, Any]:
    path = _path_for(proposal_id, root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProposalError(f"không tìm thấy proposal `{proposal_id}`") from exc
    except json.JSONDecodeError as exc:
        raise ProposalError(f"proposal `{proposal_id}` hỏng JSON: {exc}") from exc
    if payload.get("schema") != SCHEMA:
        raise ProposalError(f"proposal `{proposal_id}` sai schema")
    return payload


def save(proposal: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    _atomic_json(_path_for(str(proposal["proposal_id"]), root), proposal)
    return proposal


def _check_source(source: Path, root: Path, confirmed_doc_id: str | None = None
                  ) -> tuple[dict[str, Any], dict[str, Any]]:
    source = source.expanduser()
    if not source.is_file():
        raise ProposalError(f"file upload không tồn tại: {source}")
    if source.is_symlink():
        raise ProposalError("file upload là symlink; từ chối để tránh trỏ ngoài staging")
    source = source.resolve()
    corpus_root = root.resolve()
    protected = [corpus_root / name for name in
                 ("originals", "raw", "structured", "wiki", "derived")]
    if any(source == path or path in source.parents for path in protected):
        raise ProposalError(
            "source phải là bản upload trong staging, không được lấy trực tiếp từ corpus")
    size = source.stat().st_size
    max_bytes = int(os.getenv("KNOWLEDGE_BASE_INGEST_MAX_BYTES", str(100 * 1024 * 1024)))
    if size > max_bytes:
        raise ProposalError(f"file vượt giới hạn {max_bytes} bytes: {size}")
    kind = intake.file_kind(source)
    if kind not in ALLOWED_KINDS:
        raise ProposalError(f"loại file chưa được phép nạp: {kind} ({source.name})")
    decision = intake.decide(root, source, confirmed_doc_id=confirmed_doc_id)
    extractor = intake.extractor_for(str(decision.get("doc_id") or ""), kind)
    source_info = {
        "path": str(source),
        "name": source.name,
        "size": size,
        "sha256": _sha256(source),
        "kind": kind,
        "mime": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
        "extractor": extractor,
        "pipeline_ready": extractor in {"nexus", "spreadsheet", "markdown", "van"},
    }
    return source_info, decision


def _new_id(source_hash: str) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"ingest-{stamp}-{source_hash[:12]}"


def create(source: Path, *, actor: str, roles: str | list[str] | None = None,
           confirmed_doc_id: str | None = None,
           channel_id: str = "", thread_ts: str = "", message_ts: str = "",
           message_permalink: str = "", requester_name: str = "",
           root: Path = ROOT) -> dict[str, Any]:
    allowed, reason = authorize_requester(actor, roles, root)
    if not allowed:
        raise ProposalError(reason)
    source_info, decision = _check_source(source, root, confirmed_doc_id=confirmed_doc_id)
    proposal_id = _new_id(source_info["sha256"])
    destination = _path_for(proposal_id, root)
    while destination.exists():
        proposal_id = f"{proposal_id}-{uuid.uuid4().hex[:6]}"
        destination = _path_for(proposal_id, root)
    now = _now()
    policy = ingest_policy(root)
    flow = str(decision.get("flow") or "")
    status_by_flow = {
        "identity_review": "awaiting_identity",
        "initial_ingest": "ready_to_ingest",
        "reingest": "ready_to_ingest",
        "duplicate": "duplicate",
        "no_op": "no_op",
    }
    proposal = {
        "schema": SCHEMA,
        "proposal_id": proposal_id,
        "status": status_by_flow.get(flow, "blocked"),
        "requested_at": now,
        "requested_by": {
            "user_id": str(actor),
            "name": requester_name or str(actor),
            "roles": sorted(_roles(roles)),
        },
        "slack_context": {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "message_ts": message_ts,
            "message_permalink": message_permalink,
        },
        "source": source_info,
        "intake_decision": decision,
        "ingest_policy": policy,
        "events": [{
            "type": "proposal_created",
            "at": now,
            "actor": str(actor),
            "reason": reason,
        }],
        "review_artifact": None,
        "execution": None,
    }
    save(proposal, root)
    return proposal


def _assert_source_unchanged(proposal: dict[str, Any]) -> None:
    source = Path(str(proposal["source"]["path"])).expanduser()
    if not source.is_file():
        raise ProposalError("source đã biến mất khỏi staging; cần tạo proposal mới")
    if source.is_symlink():
        raise ProposalError("source staging đã bị thay bằng symlink; proposal bị vô hiệu")
    source = source.resolve()
    actual = _sha256(source)
    expected = str(proposal["source"]["sha256"])
    if actual != expected:
        raise ProposalError(
            f"source hash đã đổi: proposal={expected}, hiện tại={actual}; ingest bị vô hiệu")


def confirm_identity(proposal_id: str, *, doc_id: str, actor: str,
                     message_ts: str = "", message_permalink: str = "",
                     root: Path = ROOT) -> dict[str, Any]:
    """Resolve an existing document identity before ingest starts.

    Filename matching is only a candidate signal.  The trusted requester or
    one of the configured ingest users must explicitly select the document ID;
    after that, the proposal is re-evaluated against the registry.
    """
    proposal = load(proposal_id, root)
    doc_id = str(doc_id or "").strip()
    if not doc_id:
        raise ProposalError("thiếu doc_id để xác nhận identity")
    if proposal["status"] != "awaiting_identity":
        raise ProposalError(
            f"proposal đang ở trạng thái `{proposal['status']}`, không cần confirm identity")
    actor = str(actor or "").strip()
    policy = proposal.get("ingest_policy") or ingest_policy(root)
    if actor not in policy["allowed_users"]:
        raise ProposalError(f"{actor or '<empty>'} không nằm trong ingest allowlist")
    _assert_source_unchanged(proposal)
    source = Path(proposal["source"]["path"])
    source_info, decision = _check_source(source, root, confirmed_doc_id=doc_id)
    now = _now()
    proposal["source"].update(source_info)
    proposal["intake_decision"] = decision
    proposal["identity_confirmation"] = {
        "doc_id": str(doc_id),
        "confirmed_by": actor,
        "confirmed_at": now,
        "message_ts": message_ts,
        "message_permalink": message_permalink,
    }
    flow = str(decision.get("flow") or "")
    proposal["status"] = "ready_to_ingest" if flow in {
        "initial_ingest", "reingest"
    } else flow
    proposal["events"].append({
        "type": "identity_confirmed", "at": now, "actor": actor,
        "doc_id": str(doc_id), "flow": flow,
    })
    return save(proposal, root)


def attach_review_artifact(proposal_id: str, artifact: dict[str, Any],
                           *, root: Path = ROOT) -> dict[str, Any]:
    proposal = load(proposal_id, root)
    if proposal["status"] not in {"awaiting_identity", "ready_to_ingest"}:
        raise ProposalError(f"không thể gắn review artifact ở trạng thái {proposal['status']}")
    proposal["review_artifact"] = artifact
    proposal["events"].append({"type": "review_artifact_attached", "at": _now(),
                                "artifact": artifact})
    return save(proposal, root)


def proposal_message(proposal: dict[str, Any]) -> str:
    """Render the deterministic Slack status message for NexusBot."""
    policy = proposal["ingest_policy"]
    lines = [f"Proposal `{proposal['proposal_id']}` — trạng thái `{proposal['status']}`."]
    lines.append(
        f"Nguồn: `{proposal['source']['name']}` · kind={proposal['source']['kind']} · "
        f"sha256=`{proposal['source']['sha256']}`")
    decision = proposal.get("intake_decision") or {}
    lines.append(
        f"Intake: `{decision.get('flow')}` · doc_id=`{decision.get('doc_id', '—')}` · "
        f"version=`{decision.get('version', decision.get('to_version', '—'))}`")
    if proposal["status"] == "awaiting_identity":
        candidates = ", ".join(f"`{value}`" for value in decision.get("candidate_doc_ids", []))
        lines.append(
            "⚠️ Cần xác nhận document identity trước khi ingest"
            + (f": {candidates}." if candidates else ".")
        )
        return "\n".join(lines)
    if proposal["status"] in {"duplicate", "no_op"}:
        lines.append("Không tạo version corpus mới; proposal đã kết thúc.")
        return "\n".join(lines)
    if proposal.get("review_artifact"):
        artifact = proposal["review_artifact"]
        if artifact.get("url"):
            lines.append(f"Review artifact: {artifact['url']}")
        elif artifact.get("path"):
            lines.append(f"Review artifact: `{artifact['path']}`")
    requester = proposal.get("requested_by") or {}
    name = policy["allowed_users"].get(requester.get("user_id"), requester.get("user_id", "—"))
    lines.append(f"✅ Người gửi được quyền ingest: {name} ({requester.get('user_id', '—')}).")
    if proposal["status"] == "ready_to_ingest":
        lines.append("Proposal hợp lệ; worker có thể bắt đầu ingest, không cần approval.")
    return "\n".join(lines)


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Slack-triggered Knowledge Base ingest proposal")
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--file", required=True, type=Path)
    create_parser.add_argument("--actor", required=True)
    create_parser.add_argument("--roles", default="")
    create_parser.add_argument("--doc-id", default="",
                               help="xác nhận identity hiện có; bỏ trống để tạo proposal identity_review")
    create_parser.add_argument("--name", default="")
    create_parser.add_argument("--channel-id", default="")
    create_parser.add_argument("--thread-ts", default="")
    create_parser.add_argument("--message-ts", default="")
    create_parser.add_argument("--permalink", default="")

    identity_parser = sub.add_parser("confirm-identity")
    identity_parser.add_argument("proposal_id")
    identity_parser.add_argument("--doc-id", required=True)
    identity_parser.add_argument("--actor", required=True)
    identity_parser.add_argument("--message-ts", default="")
    identity_parser.add_argument("--permalink", default="")

    review_parser = sub.add_parser("review")
    review_parser.add_argument("proposal_id")
    review_parser.add_argument("--output", type=Path,
                               help="thư mục output; mặc định nằm trong proposal state")

    show_parser = sub.add_parser("show")
    show_parser.add_argument("proposal_id")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "create":
            result = create(args.file, actor=args.actor, roles=args.roles,
                            requester_name=args.name,
                            confirmed_doc_id=args.doc_id or None,
                            channel_id=args.channel_id, thread_ts=args.thread_ts,
                            message_ts=args.message_ts, message_permalink=args.permalink,
                            root=root)
        elif args.command == "confirm-identity":
            result = confirm_identity(
                args.proposal_id, doc_id=args.doc_id, actor=args.actor,
                message_ts=args.message_ts, message_permalink=args.permalink,
                root=root)
        elif args.command == "review":
            proposal = load(args.proposal_id, root)
            if proposal["status"] not in {"awaiting_identity", "ready_to_ingest"}:
                raise ProposalError(
                    f"không thể tạo review artifact ở trạng thái {proposal['status']}")
            import review_artifact  # noqa: PLC0415 - optional provider-neutral preview lane
            output = (args.output or (_proposal_dir(root) / args.proposal_id / "review"))
            artifact = review_artifact.build(
                Path(proposal["source"]["path"]), proposal_id=args.proposal_id)
            bundle = review_artifact.write_bundle(artifact, output)
            result = attach_review_artifact(args.proposal_id, bundle, root=root)
        else:
            result = load(args.proposal_id, root)
            result = {"proposal": result,
                      "message": proposal_message(result)}
    except (OSError, ProposalError, ValueError, yaml.YAMLError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
