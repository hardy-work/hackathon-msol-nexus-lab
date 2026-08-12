#!/usr/bin/env python3
"""Separate, thread-scoped conversation store for the Slack chatbot.

This module intentionally has no dependency on knowledge-base.  The only
retrieval operation exposed to callers is keyed by one canonical Slack thread.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SKILL_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_ROOT = SKILL_ROOT.parent / "knowledge-base"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_state_dir() -> Path:
    """Return a writable state directory outside the knowledge-base corpus."""
    configured = os.getenv("SLACK_THREAD_MEMORY_STATE_DIR")
    path = Path(configured).expanduser() if configured else SKILL_ROOT / ".runtime"
    path = path.resolve()
    forbidden = KNOWLEDGE_BASE_ROOT.resolve()
    if path == forbidden or forbidden in path.parents:
        raise ValueError(
            "SLACK_THREAD_MEMORY_STATE_DIR không được nằm trong knowledge-base"
        )
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_db_path() -> Path:
    return default_state_dir() / "slack-thread-memory.sqlite3"


def canonical_thread_id(channel_id: str, thread_ts: str) -> str:
    channel = str(channel_id or "").strip()
    ts = str(thread_ts or "").strip()
    if not channel or not ts or any(char.isspace() for char in (channel, ts)):
        raise ValueError("channel_id và thread_ts phải là giá trị Slack hợp lệ")
    return f"{channel}:{ts}"


_SECRET_PATTERNS = (
    (re.compile(r"(?i)\bxox[baprs]-[A-Za-z0-9-]+"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{12,})\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)(\b(?:password|passwd|secret|token)\s*[:=]\s*)[^\s,;]+"),
     r"\1[REDACTED]"),
)


def redact_text(text: str) -> str:
    value = str(text or "")
    for pattern, replacement in _SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _json(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {},
                      ensure_ascii=False, sort_keys=True)


def _safe_metadata(message: dict[str, Any]) -> dict[str, Any]:
    """Keep useful Slack metadata without persisting an unredacted payload."""
    allowed = (
        "subtype", "bot_id", "client_msg_id", "event_ts", "reply_count",
        "reactions", "files", "edited", "deleted", "permalink",
    )
    def safe(value: Any) -> Any:
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, list):
            return [safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): safe(item) for key, item in value.items()}
        return value

    result: dict[str, Any] = {}
    for key in allowed:
        if key in message:
            result[key] = safe(message[key])
    return result


class ThreadStore:
    """SQLite-backed store whose reads are always scoped to one Slack thread."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path).expanduser().resolve() if path else default_db_path()
        knowledge_root = KNOWLEDGE_BASE_ROOT.resolve()
        if self.path == knowledge_root or knowledge_root in self.path.parents:
            raise ValueError("Slack store không được đặt trong knowledge-base")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS thread(
                thread_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                thread_ts TEXT NOT NULL,
                channel_name TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(channel_id, thread_ts)
            );
            CREATE TABLE IF NOT EXISTS message(
                message_key TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL REFERENCES thread(thread_id) ON DELETE CASCADE,
                channel_id TEXT NOT NULL,
                thread_ts TEXT NOT NULL,
                message_ts TEXT NOT NULL,
                slack_message_id TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'user',
                text TEXT NOT NULL,
                permalink TEXT NOT NULL DEFAULT '',
                edited INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(thread_id, message_ts)
            );
            CREATE INDEX IF NOT EXISTS message_thread_time
                ON message(thread_id, message_ts, updated_at);
            """
        )
        self.con.commit()

    def ensure_thread(self, channel_id: str, thread_ts: str,
                      channel_name: str = "", metadata: dict[str, Any] | None = None) -> str:
        thread_id = canonical_thread_id(channel_id, thread_ts)
        now = _utc_now()
        self.con.execute(
            """INSERT INTO thread(
                thread_id, channel_id, thread_ts, channel_name, metadata, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(thread_id) DO UPDATE SET
                channel_name=CASE WHEN excluded.channel_name <> ''
                                  THEN excluded.channel_name ELSE thread.channel_name END,
                metadata=CASE WHEN excluded.metadata <> '{}'
                              THEN excluded.metadata ELSE thread.metadata END,
                updated_at=excluded.updated_at""",
            (thread_id, str(channel_id), str(thread_ts), str(channel_name or ""),
             _json(metadata), now, now),
        )
        self.con.commit()
        return thread_id

    def append_message(self, channel_id: str, thread_ts: str,
                       message: dict[str, Any], *, channel_name: str = "",
                       role: str | None = None) -> str:
        """Insert or update one Slack message; reject messages outside the scope."""
        thread_id = self.ensure_thread(channel_id, thread_ts, channel_name=channel_name)
        message_thread_ts = str(message.get("thread_ts") or message.get("ts") or "").strip()
        # The root message has no thread_ts in Slack payloads, so its own ts is
        # accepted only when it is the requested root. Replies must match it.
        if message_thread_ts != str(thread_ts):
            raise ValueError("message nằm ngoài Slack thread đang xử lý")
        message_ts = str(message.get("ts") or message.get("message_ts") or
                          message.get("deleted_ts") or "").strip()
        if not message_ts:
            raise ValueError("message thiếu ts")
        message_key = f"{channel_id}:{message_ts}"
        text = redact_text(str(message.get("text") or ""))
        subtype = str(message.get("subtype") or "")
        deleted = bool(message.get("deleted") or subtype == "message_deleted")
        edited = bool(message.get("edited") or message.get("edited_ts"))
        inferred_role = role or ("assistant" if message.get("bot_id") else "user")
        if inferred_role not in {"user", "assistant", "system"}:
            raise ValueError("role không hợp lệ")
        now = _utc_now()
        self.con.execute(
            """INSERT INTO message(
                message_key, thread_id, channel_id, thread_ts, message_ts,
                slack_message_id, user_id, role, text, permalink, edited, deleted,
                metadata, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(message_key) DO UPDATE SET
                thread_id=excluded.thread_id,
                thread_ts=excluded.thread_ts,
                slack_message_id=excluded.slack_message_id,
                user_id=excluded.user_id,
                role=excluded.role,
                text=excluded.text,
                permalink=excluded.permalink,
                edited=excluded.edited,
                deleted=excluded.deleted,
                metadata=excluded.metadata,
                updated_at=excluded.updated_at""",
            (message_key, thread_id, str(channel_id), str(thread_ts), message_ts,
             str(message.get("message_id") or message.get("client_msg_id") or ""),
             str(message.get("user_id") or message.get("user") or ""), inferred_role,
             text, str(message.get("permalink") or ""), int(edited), int(deleted),
             _json(_safe_metadata(message)), now, now),
        )
        self.con.execute("UPDATE thread SET updated_at=? WHERE thread_id=?", (now, thread_id))
        self.con.commit()
        return message_key

    def append_messages(self, channel_id: str, thread_ts: str,
                        messages: Iterable[dict[str, Any]], *, channel_name: str = "") -> int:
        count = 0
        for message in messages:
            self.append_message(channel_id, thread_ts, message, channel_name=channel_name)
            count += 1
        return count

    def set_summary(self, thread_id: str, summary: str) -> None:
        # Validate that the caller cannot accidentally write a global summary.
        self._require_thread(thread_id)
        now = _utc_now()
        self.con.execute("UPDATE thread SET summary=?, updated_at=? WHERE thread_id=?",
                         (redact_text(summary), now, thread_id))
        self.con.commit()

    def history(self, thread_id: str, limit: int = 100,
                *, include_deleted: bool = False) -> list[dict[str, Any]]:
        self._require_thread(thread_id)
        limit = max(1, min(int(limit), 1000))
        deleted_clause = "" if include_deleted else "AND deleted=0"
        rows = self.con.execute(
            f"""SELECT message_key, message_ts, slack_message_id, user_id, role,
                       text, permalink, edited, deleted, metadata
                FROM message WHERE thread_id=? {deleted_clause}
                ORDER BY message_ts, message_key LIMIT ?""",
            (thread_id, limit),
        ).fetchall()
        return [self._message_dict(row) for row in rows]

    def context(self, thread_id: str, *, recent: int = 12) -> dict[str, Any]:
        """Return only this thread's summary and recent messages."""
        row = self._require_thread(thread_id)
        messages = self.history(thread_id, limit=max(1, recent))
        return {
            "thread_id": thread_id,
            "channel_id": row["channel_id"],
            "thread_ts": row["thread_ts"],
            "summary": row["summary"],
            "messages": messages,
        }

    def delete_thread(self, thread_id: str) -> None:
        self._require_thread(thread_id)
        self.con.execute("DELETE FROM thread WHERE thread_id=?", (thread_id,))
        self.con.commit()

    def prune(self, days: int = 30) -> int:
        days = max(1, int(days))
        rows = self.con.execute(
            "SELECT thread_id FROM thread WHERE updated_at < datetime('now', ?)",
            (f"-{days} days",),
        ).fetchall()
        self.con.execute(
            "DELETE FROM thread WHERE updated_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        self.con.commit()
        return len(rows)

    def stats(self) -> dict[str, int]:
        threads = self.con.execute("SELECT COUNT(*) FROM thread").fetchone()[0]
        messages = self.con.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        return {"threads": int(threads), "messages": int(messages)}

    def _require_thread(self, thread_id: str) -> sqlite3.Row:
        row = self.con.execute("SELECT * FROM thread WHERE thread_id=?", (thread_id,)).fetchone()
        if row is None:
            raise KeyError(f"Không tìm thấy thread: {thread_id}")
        return row

    @staticmethod
    def _message_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "message_key": row["message_key"],
            "ts": row["message_ts"],
            "message_id": row["slack_message_id"],
            "user_id": row["user_id"],
            "role": row["role"],
            "text": row["text"],
            "permalink": row["permalink"],
            "edited": bool(row["edited"]),
            "deleted": bool(row["deleted"]),
            "metadata": json.loads(row["metadata"] or "{}"),
        }

    def close(self) -> None:
        self.con.close()


__all__ = [
    "ThreadStore", "canonical_thread_id", "default_db_path", "default_state_dir",
    "redact_text",
]
