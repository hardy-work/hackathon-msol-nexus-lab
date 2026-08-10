import { createHash } from "node:crypto";
import { contentToText, formatThreadContext, resolveSlackThreadScope } from "./slack_scope.mjs";

const PLUGIN_ID = "nexus-slack-thread-memory";

function logWarn(logger, message, error) {
  const detail = error instanceof Error ? `: ${error.message}` : error ? `: ${String(error)}` : "";
  logger?.warn?.(`[${PLUGIN_ID}] ${message}${detail}`);
}

function buildContext(event = {}, ctx = {}) {
  return {
    provider: ctx.messageProvider || ctx.channel || event.metadata?.provider || "",
    surface: ctx.channel || "",
    channelId: ctx.channelId || ctx.chatId || "",
    conversationId: ctx.chatId || ctx.channelId || event.from || event.to || "",
    senderId: event.senderId || ctx.senderId || event.from || "",
    messageId: event.messageId || "",
    threadTs: event.threadId || "",
    threadId: event.threadId || "",
    timestamp: event.timestamp || "",
  };
}

function sessionKeyOf(event, ctx) {
  return event.sessionKey || ctx.sessionKey || "";
}

function runKeyOf(event, ctx) {
  return event.runId || ctx.runId || "";
}

function assistantMessageTs(event, scope) {
  const explicit = String(event.messageId || "").trim();
  if (explicit) return explicit;
  const digest = createHash("sha256")
    .update(`${event.sessionKey || ""}\n${event.runId || ""}\n${event.content || ""}`)
    .digest("hex")
    .slice(0, 24);
  return `assistant:${scope.threadId}:${digest}`;
}

function remember(sessions, key, value) {
  if (!key) return;
  sessions.set(key, value);
  while (sessions.size > 2000) sessions.delete(sessions.keys().next().value);
}

export function createThreadMemoryHandlers({ store, logger } = {}) {
  if (!store) throw new Error("ThreadStore là bắt buộc");
  const sessions = new Map();

  function received(event = {}, ctx = {}) {
    const sessionKey = sessionKeyOf(event, ctx);
    const scope = resolveSlackThreadScope({ sessionKey, context: buildContext(event, ctx) });
    if (!scope) return;
    try {
      const messageKey = store.appendMessage(scope.channelId, scope.threadTs, {
        ts: scope.messageTs,
        thread_ts: scope.threadTs,
        text: contentToText(event.content),
        user_id: event.senderId || ctx.senderId || event.from || "",
        message_id: scope.messageTs,
      });
      const saved = { ...scope, messageKey, sessionKey };
      remember(sessions, runKeyOf(event, ctx), saved);
      remember(sessions, sessionKey, saved);
    } catch (error) {
      logWarn(logger, "không lưu được inbound Slack thread; tiếp tục xử lý message", error);
    }
  }

  function beforePrompt(event = {}, ctx = {}) {
    const sessionKey = sessionKeyOf(event, ctx);
    const saved = sessions.get(runKeyOf(event, ctx)) || sessions.get(sessionKey);
    const scope = saved || resolveSlackThreadScope({ sessionKey, context: buildContext(event, ctx) });
    if (!scope) return;
    try {
      const history = formatThreadContext(store.context(scope.threadId), { excludeMessageKey: saved?.messageKey || "" });
      return history ? { prependContext: history } : undefined;
    } catch (error) {
      logWarn(logger, "không đọc được context Slack thread; bỏ qua memory cho lượt này", error);
      return undefined;
    }
  }

  function sent(event = {}, ctx = {}) {
    if (event.success === false) return;
    const sessionKey = sessionKeyOf(event, ctx);
    const saved = sessions.get(runKeyOf(event, ctx)) || sessions.get(sessionKey);
    if (!saved || !event.content) return;
    try {
      store.appendMessage(saved.channelId, saved.threadTs, {
        ts: assistantMessageTs(event, saved),
        thread_ts: saved.threadTs,
        text: contentToText(event.content),
        user_id: "NexusBot",
        bot_id: "NexusBot",
        message_id: String(event.messageId || ""),
      }, { role: "assistant" });
    } catch (error) {
      logWarn(logger, "không lưu được outbound Slack thread", error);
    }
  }

  return { received, beforePrompt, sent, sessions };
}
