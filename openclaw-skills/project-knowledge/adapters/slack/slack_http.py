#!/usr/bin/env python3
"""Small Slack Events API boundary for the read-only Project Knowledge skill.

This module intentionally keeps transport concerns separate from retrieval:
signature verification and optional Slack Web API posting live here, while the
existing parser/bridge owns the answer contract.  It is suitable for a local
demo or a simple gateway; production deployments can put Bolt/Cloud Run in
front of the same bridge.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from format_message import format_result
from parse_event import parse, verify_signature
from slack_bridge import query_project
from job_queue import SlackJobQueue

SCRIPTS = next(parent / "scripts" for parent in __import__("pathlib").Path(__file__).resolve().parents
               if (parent / "scripts" / "conversation.py").exists())
import sys
sys.path.insert(0, str(SCRIPTS))
from conversation import ConversationStore
import telemetry

_worker_started = False
_worker_lock = threading.Lock()
DEFAULT_MAX_BODY_BYTES = 1024 * 1024


def max_body_bytes() -> int:
    """Return a bounded request size without trusting an invalid env value."""
    try:
        return max(1024, int(os.getenv("SLACK_MAX_BODY_BYTES", str(DEFAULT_MAX_BODY_BYTES))))
    except (TypeError, ValueError):
        return DEFAULT_MAX_BODY_BYTES


def ensure_worker() -> None:
    global _worker_started
    if os.getenv("SLACK_EMBEDDED_WORKER", "1").lower() not in {"1", "true", "yes"}:
        return
    with _worker_lock:
        if _worker_started:
            return
        from slack_worker import serve
        threading.Thread(target=serve, daemon=True, name="project-knowledge-slack-worker").start()
        _worker_started = True


def request_is_valid(headers: dict[str, str], body: bytes, secret: str) -> bool:
    """Validate Slack's timestamp/signature pair; unsigned is never implicit."""
    if not secret:
        return os.getenv("ALLOW_UNSIGNED_SLACK", "0").lower() in {"1", "true", "yes"}
    headers = {str(key).lower(): str(value) for key, value in headers.items()}
    return verify_signature(
        body,
        headers.get("x-slack-request-timestamp", ""),
        headers.get("x-slack-signature", ""),
        secret,
    )


def process_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return either a challenge or a formatted read-only response."""
    event = parse(payload)
    if event["kind"] == "url_verification":
        return {"challenge": event["challenge"]}
    if event["kind"] in {"ignored", "empty"}:
        return {
            "response_type": "ephemeral",
            "text": event.get("reason", "Hãy nhập câu hỏi dự án."),
            "metadata": {"status": "not_in_kb", "project": "nexus"},
        }
    actor = event.get("user_id", "")
    try:
        role_map = json.loads(os.getenv("PROJECT_KNOWLEDGE_SLACK_ROLE_MAP", "{}"))
    except json.JSONDecodeError:
        role_map = {}
    roles = role_map.get(actor)
    # Host-wide roles are accepted only in explicit offline demo mode. A Slack
    # user absent from the trusted map must fail closed in production.
    demo_mode = os.getenv("PROJECT_KNOWLEDGE_DEMO_MODE", "0").lower() in {"1", "true", "yes"}
    if roles is None and demo_mode:
        roles = [r.strip() for r in os.getenv("PROJECT_KNOWLEDGE_ROLES", "").split(",") if r.strip()]
    elif roles is None:
        roles = []
    session = f"slack:{event.get('channel_id', '')}:{event.get('thread_ts', '')}"
    store = ConversationStore()
    history = store.history(session)
    result = query_project(event["text"], actor=actor, roles=roles, history=history)
    store.append(session, "user", event["text"], {"event_ts": event.get("event_ts", "")})
    store.append(session, "assistant", result.get("answer", ""),
                 {"status": result.get("status", "error")})
    store.close()
    response = format_result(result, thread_ts=event.get("thread_ts", ""))
    response["metadata"].update({
        "channel_id": event.get("channel_id", ""),
        "user_id": event.get("user_id", ""),
        "event_ts": event.get("event_ts", ""),
    })
    return response


def post_to_slack(response: dict[str, Any], token: str, channel: str) -> dict[str, Any]:
    """Post a Block Kit response when a bot token is configured."""
    if not token or not channel:
        return {"ok": False, "skipped": True, "reason": "thiếu SLACK_BOT_TOKEN/channel"}
    thread_ts = response.get("thread_ts") or response.get("metadata", {}).get("event_ts")
    payload: dict[str, Any] = {
        "channel": channel,
        "text": "Nexus Project Knowledge response",
        "blocks": response.get("blocks", []),
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts
    request = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response_body:
            return json.loads(response_body.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"Slack post failed: {type(exc).__name__}: {exc}"}


class SlackHandler(BaseHTTPRequestHandler):
    server_version = "NexusSlackGateway/1.0"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP handler API
        if self.path != "/slack/events":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                raise ValueError("negative Content-Length")
            limit = max_body_bytes()
            if length > limit:
                self._json(413, {"error": "payload_too_large", "max_body_bytes": limit})
                return
            body = self.rfile.read(length)
            if not request_is_valid(dict(self.headers.items()), body,
                                    os.getenv("SLACK_SIGNING_SECRET", "")):
                self._json(401, {"error": "invalid_slack_signature"})
                return
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": f"invalid_json: {exc}"})
            return

        event = parse(payload)
        if event["kind"] == "url_verification":
            self._json(200, {"challenge": event["challenge"]})
            return

        # ACK before retrieval/model work. Slack requires a prompt response;
        # doing process_payload first made the previous implementation time out.
        token = os.getenv("SLACK_BOT_TOKEN", "")
        if token and event["kind"] == "query":
            job_id, created = SlackJobQueue().enqueue(payload)
            ensure_worker()
            telemetry.record("slack_enqueue", job_id=job_id, duplicate=not created)
            self._json(200, {"ok": True, "accepted": True, "job_id": job_id,
                             "duplicate": not created})
            return
        response = process_payload(payload)
        self._json(200, response)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._json(404, {"error": "not_found"})
            return
        self._json(200, {"ok": True, "queue": SlackJobQueue().stats(),
                         "telemetry": telemetry.summary(hours=1)})

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep the gateway quiet in demo JSON output; operators can use a real
        # logger around the process when deploying it.
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexus Slack Events API boundary")
    parser.add_argument("--host", default=os.getenv("SLACK_HTTP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("SLACK_HTTP_PORT", "8787")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), SlackHandler)
    ensure_worker()
    print(f"Nexus Slack gateway listening on http://{args.host}:{args.port}/slack/events")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
