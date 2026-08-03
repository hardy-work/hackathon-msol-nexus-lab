#!/usr/bin/env python3
"""Worker for durable Slack jobs; may run embedded or as a separate process."""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

from job_queue import SlackJobQueue

SCRIPTS = next(parent / "scripts" for parent in Path(__file__).resolve().parents
               if (parent / "scripts" / "telemetry.py").exists())
sys.path.insert(0, str(SCRIPTS))
import telemetry  # noqa: E402


def process_one(queue: SlackJobQueue | None = None) -> bool:
    queue = queue or SlackJobQueue()
    job = queue.claim()
    if job is None:
        return False
    try:
        # Late imports avoid a circular import when slack_http embeds the worker.
        from slack_http import post_to_slack, process_payload
        response = job.response or process_payload(job.payload)
        if job.response is None:
            queue.save_response(job.id, response)
        channel = response.get("metadata", {}).get("channel_id", "")
        posted = post_to_slack(response, os.getenv("SLACK_BOT_TOKEN", ""), channel)
        if not posted.get("ok"):
            raise RuntimeError(posted.get("error") or posted.get("reason") or "Slack post failed")
        queue.complete(job.id)
        telemetry.record("slack_job", job_id=job.id, state="done", attempts=job.attempts)
    except Exception as exc:
        state = queue.fail(job, f"{type(exc).__name__}: {exc}")
        telemetry.record("slack_job", job_id=job.id, state=state, attempts=job.attempts,
                         error_type=type(exc).__name__)
    return True


def serve(stop: threading.Event | None = None, poll_seconds: float = 0.5) -> None:
    stop = stop or threading.Event()
    queue = SlackJobQueue()
    while not stop.is_set():
        if not process_one(queue):
            stop.wait(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--show", type=int, metavar="JOB_ID")
    parser.add_argument("--requeue", type=int, metavar="JOB_ID")
    args = parser.parse_args()
    queue = SlackJobQueue()
    if args.stats:
        print(queue.stats())
        return 0
    if args.show is not None:
        print(queue.get(args.show))
        return 0 if queue.get(args.show) else 2
    if args.requeue is not None:
        ok = queue.requeue(args.requeue)
        print({"job_id": args.requeue, "requeued": ok})
        return 0 if ok else 2
    if args.once:
        return 0 if process_one(queue) else 2
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
