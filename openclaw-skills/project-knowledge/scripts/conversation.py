#!/usr/bin/env python3
"""Small local conversation store keyed by the Slack thread/session id."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "derived" / "conversations.sqlite3"


class ConversationStore:
    def __init__(self, path: Path = DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path, timeout=5)
        self.con.execute("""CREATE TABLE IF NOT EXISTS message(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        self.con.execute("CREATE INDEX IF NOT EXISTS message_session ON message(session,id)")

    def history(self, session: str, limit: int = 8) -> list[dict]:
        rows = self.con.execute(
            "SELECT role,content,metadata FROM message WHERE session=? ORDER BY id DESC LIMIT ?",
            (session, limit),
        ).fetchall()
        return [{"role": r, "content": c, "metadata": json.loads(m)}
                for r, c, m in reversed(rows)]

    def append(self, session: str, role: str, content: str, metadata: dict | None = None) -> None:
        self.con.execute(
            "INSERT INTO message(session,role,content,metadata) VALUES (?,?,?,?)",
            (session, role, content, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        self.con.commit()

    def close(self) -> None:
        self.con.close()
