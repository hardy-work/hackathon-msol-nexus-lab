#!/usr/bin/env python3
"""Offline contract tests for allowlisted Slack ingest proposals."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import openpyxl
import yaml

import ingest_proposal
import ingest_job
import review_artifact


INGEST_USERS = {
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
DO = "U0APQSSGKTM"


def workbook(path: Path) -> None:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Plan"
    sheet["A1"] = "Task"
    sheet["B1"] = "Hours"
    sheet["A2"] = "NEX-1"
    sheet["B2"] = 8
    sheet["C2"] = "=B2*2"
    book.save(path)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pk-ingest-proposal-") as temp:
        root = Path(temp) / "skill"
        root.mkdir()
        (root / "originals").mkdir()
        (root / "raw").mkdir()
        (root / "access.yml").write_text(
            yaml.safe_dump({"ingest": {
                "allowed_users": [
                    {"user_id": user_id, "name": name}
                    for user_id, name in INGEST_USERS.items()
                ],
            }}, sort_keys=False), encoding="utf-8")
        (root / "documents.yml").write_text("documents: []\n", encoding="utf-8")
        source = Path(temp) / "Nexus Plan.xlsx"
        workbook(source)

        state = Path(temp) / "state"
        old_state = os.environ.get("KNOWLEDGE_BASE_STATE_DIR")
        os.environ["KNOWLEDGE_BASE_STATE_DIR"] = str(state)
        try:
            try:
                ingest_proposal.create(source, actor="U_UNKNOWN", roles="project_manager", root=root)
            except ingest_proposal.ProposalError as exc:
                assert "allowlist" in str(exc)
            else:
                raise AssertionError("member ngoài allowlist không được tạo proposal")

            policy = ingest_proposal.ingest_policy(root)
            assert policy["mode"] == "slack_user_allowlist"
            assert policy["allowed_users"] == INGEST_USERS
            for user_id in INGEST_USERS:
                allowed, _ = ingest_proposal.authorize_requester(
                    user_id, roles="project_member", root=root)
                assert allowed, user_id

            proposal = ingest_proposal.create(
                source, actor=DO, requester_name="MH_DoNT", channel_id="C1",
                thread_ts="1.1", message_ts="1.2",
                message_permalink="https://slack.test/p/1", root=root)
            assert proposal["status"] == "ready_to_ingest"
            assert proposal["source"]["sha256"]
            assert proposal["source"]["kind"] == "xlsx"
            assert proposal["source"]["pipeline_ready"] is True
            assert "approval_policy" not in proposal
            assert "approvals" not in proposal
            assert not hasattr(ingest_proposal, "approve")

            artifact = review_artifact.build(source, proposal_id=proposal["proposal_id"])
            assert artifact["workbook"]["sheets"][0]["name"] == "Plan"
            cells = artifact["workbook"]["sheets"][0]["cells"]
            assert any(cell["source"] == "Plan!B2" and cell["value"] == 8 for cell in cells)
            assert any(cell["source"] == "Plan!C2" and cell["formula"] == "=B2*2"
                       for cell in cells)
            bundle = review_artifact.write_bundle(artifact, state / "review")
            assert Path(bundle["json_path"]).is_file()
            ready = ingest_proposal.attach_review_artifact(
                proposal["proposal_id"], bundle, root=root)
            message = ingest_proposal.proposal_message(ready)
            assert "MH_DoNT" in message
            assert "không cần approval" in message

            original_start = ingest_job.start
            captured = {}
            try:
                def fake_start(proposal_id, *, root, full_regression=False):
                    captured.update({"proposal_id": proposal_id, "root": root,
                                     "full_regression": full_regression})
                    return {"status": "queued", "proposal_id": proposal_id}

                ingest_job.start = fake_start
                submitted = ingest_job.submit(
                    source, actor=DO, requester_name="MH_DoNT",
                    channel_id="C1", thread_ts="1.1", message_ts="1.2",
                    root=root,
                )
            finally:
                ingest_job.start = original_start
            assert submitted["accepted"] is True
            assert submitted["job_status"] == "queued"
            submitted_proposal = ingest_proposal.load(
                submitted["proposal_id"], root
            )
            assert submitted_proposal["slack_context"]["thread_ts"] == "1.1"
            assert captured["proposal_id"] == submitted["proposal_id"]
            retried = ingest_proposal.create(
                source, actor=DO, channel_id="C1", thread_ts="1.1",
                message_ts="1.2", root=root,
            )
            assert retried["proposal_id"] == submitted["proposal_id"]

            second = ingest_proposal.create(source, actor=DO, root=root)
            source.write_bytes(source.read_bytes() + b"changed")
            try:
                ingest_proposal._assert_source_unchanged(second)
            except ingest_proposal.ProposalError as exc:
                assert "hash đã đổi" in str(exc)
            else:
                raise AssertionError("source đổi hash phải bị chặn trước ingest")

            # A filename match is not enough to select an existing identity.
            current = Path(temp) / "current.xlsx"
            workbook(current)
            (root / "originals" / "nexus-plan.xlsx").write_bytes(current.read_bytes())
            registry_hash = ingest_proposal._sha256(root / "originals" / "nexus-plan.xlsx")
            (root / "documents.yml").write_text(yaml.safe_dump({"documents": [{
                "doc_id": "nexus-plan", "version": 1,
                "original": "originals/nexus-plan.xlsx", "source_name": "Nexus Plan.xlsx",
                "kind": "xlsx", "sha256": registry_hash, "status": "canonical",
                "current": True, "supersedes": None, "visibility": "internal",
                "extractor": "nexus", "raw_paths": [],
            }]}, sort_keys=False), encoding="utf-8")
            identity_source = Path(temp) / "Nexus Plan copy.xlsx"
            workbook(identity_source)
            identity_book = openpyxl.load_workbook(identity_source)
            identity_book.active["B2"] = 9
            identity_book.save(identity_source)
            identity_proposal = ingest_proposal.create(identity_source, actor=DO, root=root)
            assert identity_proposal["status"] == "awaiting_identity"
            assert "trước khi ingest" in ingest_proposal.proposal_message(identity_proposal)
            confirmed = ingest_proposal.confirm_identity(
                identity_proposal["proposal_id"], doc_id="nexus-plan", actor=DO,
                message_permalink="https://slack.test/p/identity", root=root)
            assert confirmed["status"] == "ready_to_ingest"
            assert confirmed["identity_confirmation"]["confirmed_by"] == DO
            assert confirmed["intake_decision"]["flow"] == "reingest"
        finally:
            if old_state is None:
                os.environ.pop("KNOWLEDGE_BASE_STATE_DIR", None)
            else:
                os.environ["KNOWLEDGE_BASE_STATE_DIR"] = old_state

    print("✓ ingest proposal self-test: allowlist + hash + identity + review artifact qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
