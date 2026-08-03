#!/usr/bin/env python3
"""Smoke test Slack parsing, formatting, threading and approval proposal."""
from __future__ import annotations

import json
import hashlib
import hmac
import os
import subprocess
import sys
import time
from pathlib import Path

from parse_event import parse, verify_signature

HERE = Path(__file__).resolve().parent
BRIDGE = HERE / "slack_bridge.py"


def call(name: str) -> dict:
    payload = (HERE / "fixtures" / name).read_text(encoding="utf-8")
    env = os.environ.copy()
    env.update({"PROJECT_KNOWLEDGE_ACTOR": "local-slack-test",
                "PROJECT_KNOWLEDGE_ROLES": "project_member"})
    proc = subprocess.run([sys.executable, str(BRIDGE)], input=payload, text=True,
                          capture_output=True, check=False, env=env)
    if proc.returncode:
        raise RuntimeError(f"{name}: {proc.stderr}")
    return json.loads(proc.stdout)


def main() -> int:
    mention = call("app_mention.json")
    assert mention["metadata"]["status"] == "in_kb"
    assert mention["thread_ts"] == "1720000000.000001"
    assert mention["metadata"]["channel_id"] == "C_NEXUS"

    action = call("action_request.json")
    elements = [e for block in action["blocks"] for e in block.get("elements", [])]
    assert action["metadata"]["status"] == "not_in_kb"
    assert any(e.get("action_id", "").startswith("project_action_approve") for e in elements)
    assert all(json.loads(e["value"])["requires_approval"] for e in elements if "value" in e)

    verification = call("url_verification.json")
    assert verification == {"challenge": "nexus-demo-challenge"}

    slash = parse({"command": "/nexus", "user_id": "U1", "channel_id": "C1",
                   "text": "ĐôNT làm vai trò gì?", "thread_ts": "123.456"})
    assert slash["kind"] == "query" and slash["thread_ts"] == "123.456"

    bot = parse({"type": "event_callback", "event": {"type": "message",
                "bot_id": "B1", "text": "bot reply", "channel": "C1", "ts": "1"}})
    assert bot["kind"] == "ignored"

    empty = parse({"type": "event_callback", "event": {"type": "message",
                  "user": "U1", "channel": "C1", "ts": "1", "text": ""}})
    assert empty["kind"] == "empty"

    secret, timestamp, body = "local-secret", str(int(time.time())), b'{"type":"event_callback"}'
    base = b"v0:" + timestamp.encode() + b":" + body
    signature = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    assert verify_signature(body, timestamp, signature, secret)
    assert not verify_signature(body, timestamp, signature + "x", secret)

    print("✓ slack adapter self-test: 8/8 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
