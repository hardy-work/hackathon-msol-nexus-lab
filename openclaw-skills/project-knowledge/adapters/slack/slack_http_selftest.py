#!/usr/bin/env python3
"""Offline tests for the Slack HTTP boundary; no token or network required."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

from slack_http import process_payload, request_is_valid


HERE = Path(__file__).resolve().parent


def main() -> int:
    app = json.loads((HERE / "fixtures/app_mention.json").read_text(encoding="utf-8"))
    response = process_payload(app)
    assert response["metadata"]["status"] == "in_kb"
    assert response["metadata"]["channel_id"] == "C_NEXUS"
    assert response["thread_ts"] == "1720000000.000001"

    challenge = process_payload({"type": "url_verification", "challenge": "abc"})
    assert challenge == {"challenge": "abc"}

    body = b'{"type":"event_callback"}'
    secret, timestamp = "local-secret", str(int(time.time()))
    base = b"v0:" + timestamp.encode() + b":" + body
    signature = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    assert request_is_valid({"X-Slack-Request-Timestamp": timestamp,
                             "X-Slack-Signature": signature}, body, secret)
    assert not request_is_valid({"X-Slack-Request-Timestamp": timestamp,
                                 "X-Slack-Signature": "v0=bad"}, body, secret)
    assert not request_is_valid({}, body, secret)

    print("✓ slack HTTP boundary self-test: 5/5 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
