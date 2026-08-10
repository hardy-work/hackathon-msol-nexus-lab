import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createThreadMemoryHandlers } from "../runtime/handlers.mjs";
import { ThreadStore } from "../runtime/thread_store.mjs";

const sessionKey = "agent:main:slack:channel:C12345678:thread:1712345678.123456";
const hookContext = { messageProvider: "slack", channelId: "C12345678", sessionKey };

test("typed hooks store inbound/outbound and return context for the real prompt hook", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nexus-hook-"));
  const store = new ThreadStore(path.join(dir, "threads.sqlite3"));
  const handlers = createThreadMemoryHandlers({ store, logger: { warn: assert.fail } });
  handlers.received({ sessionKey, runId: "run-1", threadId: "1712345678.123456", messageId: "1712345680.000001", content: "quyết định gì?", from: "U1", senderId: "U1" }, hookContext);
  handlers.sent({ sessionKey, runId: "run-1", success: true, content: "Dùng ThreadStore." }, hookContext);
  handlers.received({ sessionKey, runId: "run-2", threadId: "1712345678.123456", messageId: "1712345681.000001", content: "áp dụng thế nào?", from: "U1", senderId: "U1" }, hookContext);
  const result = handlers.beforePrompt({ prompt: "áp dụng thế nào?", runId: "run-2", sessionKey }, { ...hookContext, runId: "run-2" });
  assert.match(result.prependContext, /slack_thread_history/);
  assert.match(result.prependContext, /Dùng ThreadStore/);
  assert.equal(store.stats().messages, 3);
  assert.deepEqual(store.context("C12345678:1712345678.123456").messages.map((m) => m.role), ["user", "assistant", "user"]);
  store.close();
  fs.rmSync(dir, { recursive: true, force: true });
});
