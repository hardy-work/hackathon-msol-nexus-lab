#!/usr/bin/env python3
"""Privacy-preserving operational telemetry for Project Knowledge."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from runtime_state import state_path

ROOT = Path(__file__).resolve().parent.parent
DB = state_path("telemetry.sqlite3")


def question_hash(question: str) -> str:
    return hashlib.sha256(question.strip().encode("utf-8")).hexdigest()[:16]


def record(event: str, *, path: Path = DB, **fields) -> None:
    """Record metadata only; raw questions, answers and actor IDs are forbidden."""
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {key: value for key, value in fields.items()
            if key not in {"query", "question", "answer", "actor", "content"}}
    con = None
    try:
        con = sqlite3.connect(path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""CREATE TABLE IF NOT EXISTS event(
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL,
            event TEXT NOT NULL, fields TEXT NOT NULL)""")
        con.execute("INSERT INTO event(created_at,event,fields) VALUES (?,?,?)",
                    (time.time(), event, json.dumps(safe, ensure_ascii=False, sort_keys=True)))
        con.execute("DELETE FROM event WHERE created_at < ?", (time.time() - 30 * 86400,))
        con.commit()
    except sqlite3.Error:
        # Observability must never turn a valid knowledge answer into an error.
        return
    finally:
        if con is not None:
            con.close()


def summary(path: Path = DB, hours: int = 24) -> dict:
    if not path.exists():
        return {"events": 0, "by_event": {}}
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT event,fields FROM event WHERE created_at>=?", (time.time() - hours * 3600,)
        ).fetchall()
    finally:
        con.close()
    by_event: dict[str, int] = {}
    latencies = []
    cache_hits = 0
    for event, payload in rows:
        by_event[event] = by_event.get(event, 0) + 1
        fields = json.loads(payload)
        if fields.get("duration_ms") is not None:
            latencies.append(float(fields["duration_ms"]))
        cache_hits += bool(fields.get("cache_hit"))
    latencies.sort()
    percentile = lambda p: latencies[min(int(len(latencies) * p), len(latencies) - 1)] if latencies else None
    return {"events": len(rows), "by_event": by_event, "cache_hits": cache_hits,
            "latency_p50_ms": percentile(0.50), "latency_p95_ms": percentile(0.95)}
