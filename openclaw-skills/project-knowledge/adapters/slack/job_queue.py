#!/usr/bin/env python3
"""Durable, idempotent Slack delivery queue with retry and dead-letter state."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILL = next(parent for parent in Path(__file__).resolve().parents
             if (parent / "scripts" / "answer.py").exists())
DB = Path(os.getenv("PROJECT_KNOWLEDGE_STATE_DIR", str(SKILL / ".runtime"))) / "slack_jobs.sqlite3"


def event_key(payload: dict[str, Any]) -> str:
    if payload.get("event_id"):
        return str(payload["event_id"])
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    stable = {"team": payload.get("team_id", ""), "channel": event.get("channel", payload.get("channel_id", "")),
              "user": event.get("user", payload.get("user_id", "")),
              "ts": event.get("ts", payload.get("timestamp", "")),
              "text": event.get("text", payload.get("text", ""))}
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "derived:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Job:
    id: int
    event_key: str
    payload: dict[str, Any]
    attempts: int
    response: dict[str, Any] | None


class SlackJobQueue:
    def __init__(self, path: Path | None = None):
        path = path or Path(os.getenv("SLACK_JOB_DB", str(DB)))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=15000")
        return con

    def _init(self) -> None:
        con = self._connect()
        try:
            con.execute("""CREATE TABLE IF NOT EXISTS job(
                id INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL, response TEXT, state TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at REAL NOT NULL DEFAULT 0,
                locked_at REAL, last_error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL)""")
            con.execute("CREATE INDEX IF NOT EXISTS job_ready ON job(state,next_attempt_at,id)")
        finally:
            con.close()

    def enqueue(self, payload: dict[str, Any]) -> tuple[int, bool]:
        key, now = event_key(payload), time.time()
        con = self._connect()
        try:
            retention = max(1, int(os.getenv("SLACK_JOB_RETENTION_DAYS", "30")))
            con.execute("DELETE FROM job WHERE state='done' AND updated_at<?",
                        (now - retention * 86400,))
            cur = con.execute("""INSERT OR IGNORE INTO job(
                event_key,payload,created_at,updated_at) VALUES (?,?,?,?)""",
                (key, json.dumps(payload, ensure_ascii=False), now, now))
            row = con.execute("SELECT id FROM job WHERE event_key=?", (key,)).fetchone()
            return int(row[0]), cur.rowcount == 1
        finally:
            con.close()

    def claim(self, lease_seconds: int = 300) -> Job | None:
        now = time.time()
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("""UPDATE job SET state='pending',locked_at=NULL,updated_at=?
                WHERE state='running' AND locked_at<?""", (now, now - lease_seconds))
            row = con.execute("""SELECT id,event_key,payload,attempts,response FROM job
                WHERE state='pending' AND next_attempt_at<=? ORDER BY id LIMIT 1""", (now,)).fetchone()
            if row is None:
                con.execute("COMMIT")
                return None
            attempts = int(row[3]) + 1
            con.execute("""UPDATE job SET state='running',attempts=?,locked_at=?,updated_at=?
                WHERE id=?""", (attempts, now, now, row[0]))
            con.execute("COMMIT")
            return Job(int(row[0]), str(row[1]), json.loads(row[2]), attempts,
                       json.loads(row[4]) if row[4] else None)
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def save_response(self, job_id: int, response: dict[str, Any]) -> None:
        con = self._connect()
        try:
            con.execute("UPDATE job SET response=?,updated_at=? WHERE id=?",
                        (json.dumps(response, ensure_ascii=False), time.time(), job_id))
        finally:
            con.close()

    def complete(self, job_id: int) -> None:
        con = self._connect()
        try:
            con.execute("UPDATE job SET state='done',locked_at=NULL,last_error=NULL,updated_at=? WHERE id=?",
                        (time.time(), job_id))
        finally:
            con.close()

    def fail(self, job: Job, error: str) -> str:
        max_attempts = max(1, int(os.getenv("SLACK_JOB_MAX_ATTEMPTS", "5")))
        state = "dead" if job.attempts >= max_attempts else "pending"
        base = max(1, int(os.getenv("SLACK_JOB_RETRY_BASE_SECONDS", "2")))
        next_at = time.time() + base * (2 ** max(0, job.attempts - 1))
        con = self._connect()
        try:
            con.execute("""UPDATE job SET state=?,next_attempt_at=?,locked_at=NULL,
                last_error=?,updated_at=? WHERE id=?""",
                (state, next_at, error[:1000], time.time(), job.id))
        finally:
            con.close()
        return state

    def get(self, job_id: int) -> dict[str, Any] | None:
        con = self._connect()
        try:
            row = con.execute("""SELECT id,event_key,state,attempts,next_attempt_at,last_error,
                created_at,updated_at FROM job WHERE id=?""", (job_id,)).fetchone()
            if row is None:
                return None
            keys = ("id", "event_key", "state", "attempts", "next_attempt_at", "last_error",
                    "created_at", "updated_at")
            return dict(zip(keys, row))
        finally:
            con.close()

    def requeue(self, job_id: int, reset_attempts: bool = True) -> bool:
        con = self._connect()
        try:
            attempts = 0 if reset_attempts else None
            if attempts is None:
                cur = con.execute("""UPDATE job SET state='pending',next_attempt_at=0,
                    locked_at=NULL,last_error=NULL,updated_at=? WHERE id=? AND state='dead'""",
                    (time.time(), job_id))
            else:
                cur = con.execute("""UPDATE job SET state='pending',attempts=?,next_attempt_at=0,
                    locked_at=NULL,last_error=NULL,updated_at=? WHERE id=? AND state='dead'""",
                    (attempts, time.time(), job_id))
            return cur.rowcount == 1
        finally:
            con.close()

    def stats(self) -> dict[str, int]:
        con = self._connect()
        try:
            return {str(state): int(count) for state, count in
                    con.execute("SELECT state,count(*) FROM job GROUP BY state").fetchall()}
        finally:
            con.close()
