#!/usr/bin/env python3
"""Version- and access-scoped query cache for the read-only runtime."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import os
import time
from pathlib import Path
from runtime_state import state_path

ROOT = Path(__file__).resolve().parent.parent
DB = state_path("query_cache.sqlite3")


def cache_key(project: str, query: str, version: str, access_fingerprint: str,
              llm: bool, history: list[dict] | None = None) -> str:
    payload = json.dumps({
        "project": project,
        "query": query.strip(),
        "version": version,
        "access": access_fingerprint,
        "llm": bool(llm),
        "history": history or [],
        "citation_format": "source-v1",
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class QueryCache:
    def __init__(self, path: Path = DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path, timeout=5, check_same_thread=False)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("""CREATE TABLE IF NOT EXISTS cache(
            key TEXT PRIMARY KEY, version TEXT NOT NULL, payload TEXT NOT NULL,
            created_at REAL NOT NULL DEFAULT 0, expires_at REAL)""")
        columns = {row[1] for row in self.con.execute("PRAGMA table_info(cache)").fetchall()}
        if "expires_at" not in columns:
            self.con.execute("ALTER TABLE cache ADD COLUMN expires_at REAL")

    def get(self, key: str) -> dict | None:
        row = self.con.execute(
            "SELECT payload FROM cache WHERE key=? AND (expires_at IS NULL OR expires_at>?)",
            (key, time.time()),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, version: str, payload: dict) -> None:
        now = time.time()
        ttl = max(60, int(os.getenv("KNOWLEDGE_BASE_CACHE_TTL_SECONDS", "86400")))
        self.con.execute("""INSERT OR REPLACE INTO cache(
            key,version,payload,created_at,expires_at) VALUES (?,?,?,?,?)""",
            (key, version, json.dumps(payload, ensure_ascii=False), now, now + ttl))
        max_rows = max(100, int(os.getenv("KNOWLEDGE_BASE_CACHE_MAX_ROWS", "10000")))
        self.con.execute("DELETE FROM cache WHERE expires_at IS NOT NULL AND expires_at<=?", (now,))
        self.con.execute("""DELETE FROM cache WHERE key IN (
            SELECT key FROM cache ORDER BY created_at DESC LIMIT -1 OFFSET ?)""", (max_rows,))
        self.con.commit()

    def close(self) -> None:
        self.con.close()
