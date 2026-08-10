import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const SKILL_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PROJECT_KNOWLEDGE_ROOT = path.resolve(SKILL_ROOT, "../project-knowledge");

function utcNow() {
  return new Date().toISOString();
}

function isWithin(candidate, parent) {
  const relative = path.relative(parent, candidate);
  return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}

export function defaultStateDir() {
  const configured = process.env.SLACK_THREAD_MEMORY_STATE_DIR?.trim();
  const stateRoot = process.env.OPENCLAW_STATE_DIR?.trim() || path.join(os.homedir(), ".openclaw-hackathon");
  const dir = path.resolve(configured || path.join(stateRoot, "state", "slack-thread-memory"));
  if (isWithin(dir, path.resolve(PROJECT_KNOWLEDGE_ROOT))) {
    throw new Error("SLACK_THREAD_MEMORY_STATE_DIR không được nằm trong project-knowledge");
  }
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

export function defaultDbPath() {
  return path.join(defaultStateDir(), "slack-thread-memory.sqlite3");
}

export function canonicalThreadId(channelId, threadTs) {
  const channel = String(channelId || "").trim();
  const ts = String(threadTs || "").trim();
  if (!channel || !ts || /\s/.test(channel) || /\s/.test(ts)) {
    throw new Error("channel_id và thread_ts phải là giá trị Slack hợp lệ");
  }
  return `${channel}:${ts}`;
}

const SECRET_PATTERNS = [
  [/\b(xox[baprs]-[A-Za-z0-9-]+)/gi, "[REDACTED_SLACK_TOKEN]"],
  [/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [REDACTED]"],
  [/\bsk-[A-Za-z0-9_-]{12,}\b/gi, "[REDACTED_API_KEY]"],
  [/\b(password|passwd|secret|token)\s*[:=]\s*(?!\[REDACTED(?:_[A-Z_]+)?\])[^\s,;]+/gi, "$1: [REDACTED]"],
];

export function redactText(value) {
  let text = String(value || "");
  for (const [pattern, replacement] of SECRET_PATTERNS) text = text.replace(pattern, replacement);
  return text;
}

function safeJson(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "{}";
  return JSON.stringify(redactValue(value));
}

function redactValue(value) {
  if (typeof value === "string") return redactText(value);
  if (Array.isArray(value)) return value.map(redactValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, redactValue(item)]));
  }
  return value;
}

function safeMetadata(message) {
  const allowed = [
    "subtype", "bot_id", "client_msg_id", "event_ts", "reply_count",
    "reactions", "files", "edited", "deleted", "permalink",
  ];
  return Object.fromEntries(allowed.filter((key) => key in message).map((key) => [key, message[key]]));
}

export class ThreadStore {
  constructor(dbPath = undefined) {
    this.path = path.resolve(String(dbPath || defaultDbPath()));
    if (isWithin(this.path, path.resolve(PROJECT_KNOWLEDGE_ROOT))) {
      throw new Error("Slack store không được đặt trong project-knowledge");
    }
    fs.mkdirSync(path.dirname(this.path), { recursive: true });
    this.db = new DatabaseSync(this.path);
    this.db.exec("PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL;");
    this.db.exec(`
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
      CREATE INDEX IF NOT EXISTS message_thread_time ON message(thread_id, message_ts, updated_at);
    `);
    this.db.exec("PRAGMA busy_timeout=5000;");
  }

  ensureThread(channelId, threadTs, { channelName = "", metadata = {} } = {}) {
    const threadId = canonicalThreadId(channelId, threadTs);
    const now = utcNow();
    this.db.prepare(`
      INSERT INTO thread(thread_id, channel_id, thread_ts, channel_name, metadata, created_at, updated_at)
      VALUES(?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(thread_id) DO UPDATE SET
        channel_name=CASE WHEN excluded.channel_name <> '' THEN excluded.channel_name ELSE thread.channel_name END,
        metadata=CASE WHEN excluded.metadata <> '{}' THEN excluded.metadata ELSE thread.metadata END,
        updated_at=excluded.updated_at
    `).run(threadId, String(channelId), String(threadTs), String(channelName || ""), safeJson(metadata), now, now);
    return threadId;
  }

  appendMessage(channelId, threadTs, message, { channelName = "", role = undefined } = {}) {
    const threadId = this.ensureThread(channelId, threadTs, { channelName });
    const messageThreadTs = String(message.thread_ts || message.ts || "").trim();
    if (messageThreadTs !== String(threadTs)) throw new Error("message nằm ngoài Slack thread đang xử lý");
    const messageTs = String(message.ts || message.message_ts || message.deleted_ts || "").trim();
    if (!messageTs) throw new Error("message thiếu ts");
    const messageKey = `${channelId}:${messageTs}`;
    const inferredRole = role || (message.bot_id ? "assistant" : "user");
    if (!["user", "assistant", "system"].includes(inferredRole)) throw new Error("role không hợp lệ");
    const now = utcNow();
    this.db.prepare(`
      INSERT INTO message(
        message_key, thread_id, channel_id, thread_ts, message_ts, slack_message_id,
        user_id, role, text, permalink, edited, deleted, metadata, created_at, updated_at
      ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(message_key) DO UPDATE SET
        thread_id=excluded.thread_id, thread_ts=excluded.thread_ts,
        slack_message_id=excluded.slack_message_id, user_id=excluded.user_id,
        role=excluded.role, text=excluded.text, permalink=excluded.permalink,
        edited=excluded.edited, deleted=excluded.deleted, metadata=excluded.metadata,
        updated_at=excluded.updated_at
    `).run(
      messageKey, threadId, String(channelId), String(threadTs), messageTs,
      String(message.message_id || message.client_msg_id || ""),
      String(message.user_id || message.user || ""), inferredRole,
      redactText(message.text || ""), String(message.permalink || ""),
      Number(Boolean(message.edited || message.edited_ts)),
      Number(Boolean(message.deleted || message.subtype === "message_deleted")),
      safeJson(safeMetadata(message)), now, now,
    );
    this.db.prepare("UPDATE thread SET updated_at=? WHERE thread_id=?").run(now, threadId);
    return messageKey;
  }

  setSummary(threadId, summary) {
    this.requireThread(threadId);
    this.db.prepare("UPDATE thread SET summary=?, updated_at=? WHERE thread_id=?").run(redactText(summary), utcNow(), threadId);
  }

  history(threadId, limit = 100, { includeDeleted = false } = {}) {
    this.requireThread(threadId);
    const safeLimit = Math.max(1, Math.min(Number(limit) || 1, 1000));
    const deletedClause = includeDeleted ? "" : "AND deleted=0";
    return this.db.prepare(`
      SELECT message_key, message_ts, slack_message_id, user_id, role, text,
             permalink, edited, deleted, metadata
      FROM message WHERE thread_id=? ${deletedClause}
      ORDER BY rowid LIMIT ?
    `).all(threadId, safeLimit).map((row) => ({
      message_key: row.message_key,
      ts: row.message_ts,
      message_id: row.slack_message_id,
      user_id: row.user_id,
      role: row.role,
      text: row.text,
      permalink: row.permalink,
      edited: Boolean(row.edited),
      deleted: Boolean(row.deleted),
      metadata: JSON.parse(row.metadata || "{}"),
    }));
  }

  context(threadId, { recent = 12 } = {}) {
    const row = this.requireThread(threadId);
    return {
      thread_id: threadId,
      channel_id: row.channel_id,
      thread_ts: row.thread_ts,
      summary: row.summary,
      messages: this.history(threadId, Math.max(1, recent)),
    };
  }

  stats() {
    return {
      threads: Number(this.db.prepare("SELECT COUNT(*) AS count FROM thread").get().count),
      messages: Number(this.db.prepare("SELECT COUNT(*) AS count FROM message").get().count),
    };
  }

  requireThread(threadId) {
    const row = this.db.prepare("SELECT * FROM thread WHERE thread_id=?").get(threadId);
    if (!row) throw new Error(`Không tìm thấy thread: ${threadId}`);
    return row;
  }

  close() {
    this.db.close();
  }
}
