import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { ThreadStore } from "../runtime/thread_store.mjs";

test("ThreadStore is thread-scoped, redacts secrets, and is retry-idempotent", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nexus-thread-store-"));
  const store = new ThreadStore(path.join(dir, "threads.sqlite3"));
  const thread = "C12345678:1712345678.123456";
  const message = {
    ts: "1712345678.123456",
    thread_ts: "1712345678.123456",
    text: "token=xoxb-secret Bearer abc",
    user_id: "U1",
  };
  store.appendMessage("C12345678", "1712345678.123456", message);
  store.appendMessage("C12345678", "1712345678.123456", message);
  store.appendMessage("C12345678", "1712345678.123457", {
    ts: "1712345678.123457", thread_ts: "1712345678.123457", text: "other thread", user_id: "U2",
  });
  const context = store.context(thread);
  assert.equal(context.messages.length, 1);
  assert.match(context.messages[0].text, /REDACTED_SLACK_TOKEN/);
  assert.doesNotMatch(context.messages[0].text, /xoxb-secret/);
  assert.equal(store.stats().messages, 2);
  assert.throws(() => store.appendMessage("C12345678", "1712345678.123456", {
    ts: "1712345678.123458", thread_ts: "1712345678.999999", text: "wrong scope",
  }), /ngoài Slack thread/);
  store.close();
  fs.rmSync(dir, { recursive: true, force: true });
});
