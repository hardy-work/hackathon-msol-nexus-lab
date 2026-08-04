#!/usr/bin/env python3
"""Offline tests for the Slack HTTP boundary; no token or network required."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import time
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from slack_http import SlackHandler, process_payload, request_is_valid


HERE = Path(__file__).resolve().parent


def main() -> int:
    os.environ["PROJECT_KNOWLEDGE_SLACK_ROLE_MAP"] = '{"U_DEMO":["project_member"]}'
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

    # Real HTTP boundary: ACK/enqueue happens without running retrieval or a
    # network post, and retrying the same Slack event is idempotent.
    with tempfile.TemporaryDirectory(prefix="pk-slack-http-") as temp:
        os.environ.update({"SLACK_SIGNING_SECRET": secret, "SLACK_BOT_TOKEN": "xoxb-test",
                           "SLACK_EMBEDDED_WORKER": "0",
                           "SLACK_MAX_BODY_BYTES": "1048576",
                           "SLACK_JOB_DB": str(Path(temp) / "jobs.sqlite3")})
        server = ThreadingHTTPServer(("127.0.0.1", 0), SlackHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        event = {"type": "event_callback", "event_id": "Ev-http-1", "event": {
            "type": "app_mention", "user": "U_DEMO", "channel": "C_NEXUS",
            "ts": "1720000000.000009", "text": "<@U_BOT> câu hỏi chậm"}}
        raw = json.dumps(event).encode("utf-8")
        ts = str(int(time.time()))
        sig = "v0=" + hmac.new(secret.encode(), b"v0:" + ts.encode() + b":" + raw,
                                hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/slack/events", data=raw,
            headers={"Content-Type": "application/json", "X-Slack-Request-Timestamp": ts,
                     "X-Slack-Signature": sig}, method="POST")
        started = time.perf_counter()
        first = json.loads(urllib.request.urlopen(req, timeout=2).read())
        elapsed = time.perf_counter() - started
        second = json.loads(urllib.request.urlopen(req, timeout=2).read())
        assert elapsed < 1.0 and first["accepted"] and not first["duplicate"]
        assert second["duplicate"] and second["job_id"] == first["job_id"]

        # Reject an oversized request before reading its body or checking HMAC.
        oversized = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        oversized.request("POST", "/slack/events", body=b"", headers={
            "Content-Type": "application/json",
            "Content-Length": str(int(os.environ["SLACK_MAX_BODY_BYTES"]) + 1),
        })
        limited = oversized.getresponse()
        assert limited.status == 413
        limited.read()
        oversized.close()
        server.shutdown(); server.server_close(); thread.join(timeout=2)

    print("✓ slack HTTP boundary self-test: 8/8 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
