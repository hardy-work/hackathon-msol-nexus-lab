import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { ThreadStore } from "../runtime/thread_store.mjs";
import { createThreadMemoryHandlers } from "../runtime/handlers.mjs";

const PLUGIN_ID = "nexus-slack-thread-memory";

export { createThreadMemoryHandlers } from "../runtime/handlers.mjs";

export default definePluginEntry({
  id: PLUGIN_ID,
  name: "Nexus Slack Thread Memory",
  description: "Lưu context theo từng Slack thread trong chính gateway của NexusBot.",
  register(api) {
    const store = new ThreadStore();
    const handlers = createThreadMemoryHandlers({ store, logger: api.logger });
    api.on("message_received", handlers.received);
    api.on("before_prompt_build", handlers.beforePrompt, { timeoutMs: 500 });
    api.on("message_sent", handlers.sent);
    api.logger?.info?.(`[${PLUGIN_ID}] enabled: typed prompt hook, no Slack app_mention or LLM adapter registered`);
  },
});
