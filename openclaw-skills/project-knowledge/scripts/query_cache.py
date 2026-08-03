#!/usr/bin/env python3
"""Version- and access-scoped query cache for the read-only runtime."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "derived" / "query_cache.sqlite3"


def cache_key(project: str, query: str, version: str, access_fingerprint: str,
              llm: bool, history: list[dict] | None = None) -> str:
    payload = json.dumps({
        "project": project,
        "query": query.strip(),
        "version": version,
        "access": access_fingerprint,
        "llm": bool(llm),
        "history": history or [],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class QueryCache:
    def __init__(self, path: Path = DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path, timeout=5)
        self.con.execute("""CREATE TABLE IF NOT EXISTS cache(
            key TEXT PRIMARY KEY, version TEXT NOT NULL, payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

    def get(self, key: str) -> dict | None:
        row = self.con.execute("SELECT payload FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, version: str, payload: dict) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO cache(key,version,payload) VALUES (?,?,?)",
            (key, version, json.dumps(payload, ensure_ascii=False)),
        )
        self.con.commit()

    def close(self) -> None:
        self.con.close()
