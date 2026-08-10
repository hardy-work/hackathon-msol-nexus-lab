import test from "node:test";
import assert from "node:assert/strict";
import { formatThreadContext, resolveSlackThreadScope } from "../runtime/slack_scope.mjs";

test("resolves Slack channel and thread from the trusted session key", () => {
  const scope = resolveSlackThreadScope({
    sessionKey: "agent:main:slack:channel:C12345678:thread:1712345678.123456",
    context: { provider: "slack", messageId: "1712345680.000001", body: "hello" },
  });
  assert.deepEqual(scope, {
    channelId: "C12345678",
    threadTs: "1712345678.123456",
    messageTs: "1712345680.000001",
    threadId: "C12345678:1712345678.123456",
    messageKey: "C12345678:1712345680.000001",
  });
});
test("does not accept a non-Slack event or user supplied thread text", () => {
  assert.equal(resolveSlackThreadScope({ sessionKey: "agent:main:web:chat", context: { body: "C12345678:1.2" } }), null);
});

test("formats only the selected thread and marks history as untrusted", () => {
  const result = formatThreadContext({
    summary: "đã thống nhất format",
    messages: [
      { message_key: "C1:1.1", role: "user", user_id: "U1", text: "old" },
      { message_key: "C1:1.2", role: "assistant", text: "token=xoxb-secret" },
    ],
  }, { excludeMessageKey: "C1:1.1" });
  assert.match(result, /untrusted conversation history/);
  assert.doesNotMatch(result, /old/);
  assert.match(result, /REDACTED_SLACK_TOKEN/);
});
