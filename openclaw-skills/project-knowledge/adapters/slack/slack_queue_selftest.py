#!/usr/bin/env python3
"""Offline concurrency/retry/dead-letter tests for the durable Slack queue."""
from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from job_queue import SlackJobQueue


def main() -> int:
    old_attempts = os.environ.get("SLACK_JOB_MAX_ATTEMPTS")
    old_base = os.environ.get("SLACK_JOB_RETRY_BASE_SECONDS")
    os.environ["SLACK_JOB_MAX_ATTEMPTS"] = "2"
    os.environ["SLACK_JOB_RETRY_BASE_SECONDS"] = "1"
    try:
        with tempfile.TemporaryDirectory(prefix="pk-slack-queue-") as temp:
            queue = SlackJobQueue(Path(temp) / "jobs.sqlite3")
            payload = {"event_id": "Ev-1", "event": {"type": "app_mention", "ts": "1",
                       "channel": "C1", "user": "U1", "text": "question"}}
            with ThreadPoolExecutor(max_workers=8) as pool:
                enqueued = list(pool.map(lambda _: queue.enqueue(payload), range(8)))
            ids = {item[0] for item in enqueued}
            assert len(ids) == 1 and sum(item[1] for item in enqueued) == 1

            job = queue.claim()
            assert job and job.attempts == 1
            queue.save_response(job.id, {"metadata": {"channel_id": "C1"}, "blocks": []})
            assert queue.fail(job, "temporary") == "pending"
            time.sleep(1.05)
            retry = queue.claim()
            assert retry and retry.attempts == 2 and retry.response is not None
            assert queue.fail(retry, "permanent") == "dead"
            assert queue.stats() == {"dead": 1}
            assert queue.requeue(retry.id)
            replay = queue.claim()
            assert replay and replay.attempts == 1 and replay.response is not None
            queue.complete(replay.id)
            assert queue.stats() == {"done": 1}

            # Worker persists the formatted response: a delivery retry must not
            # run retrieval/model generation twice.
            import slack_http
            import slack_worker
            calls = {"query": 0, "post": 0}
            original_process, original_post = slack_http.process_payload, slack_http.post_to_slack
            def fake_process(_payload):
                calls["query"] += 1
                return {"metadata": {"channel_id": "C1"}, "blocks": []}
            def fake_post(_response, _token, _channel):
                calls["post"] += 1
                return {"ok": calls["post"] > 1, "error": "temporary"}
            slack_http.process_payload, slack_http.post_to_slack = fake_process, fake_post
            os.environ["SLACK_BOT_TOKEN"] = "xoxb-test"
            try:
                queue.enqueue({"event_id": "Ev-2", "event": {"ts": "2"}})
                assert slack_worker.process_one(queue)
                time.sleep(1.05)
                assert slack_worker.process_one(queue)
                assert calls == {"query": 1, "post": 2}
            finally:
                slack_http.process_payload, slack_http.post_to_slack = original_process, original_post
    finally:
        if old_attempts is None:
            os.environ.pop("SLACK_JOB_MAX_ATTEMPTS", None)
        else:
            os.environ["SLACK_JOB_MAX_ATTEMPTS"] = old_attempts
        if old_base is None:
            os.environ.pop("SLACK_JOB_RETRY_BASE_SECONDS", None)
        else:
            os.environ["SLACK_JOB_RETRY_BASE_SECONDS"] = old_base
    print("✓ slack durable queue self-test: 11/11 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
