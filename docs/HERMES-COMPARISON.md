# Scope relative to Hermes Agent

Reference: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent), inspected October 15, 2026. Hermes is a broader agent platform. This comparison addresses architecture and workflow, not equal reasoning performance. Skylinee remains its own codebase, using Ollama; no Hermes code is vendored.

| Capability | Skylinee 0.1 upload | Skylinee 0.6 release | Remaining difference |
|---|---|---|---|
| Multi-step tool execution | No | Native Ollama tool calls, all calls returned, bounded loop | Smaller tool catalog; no tool marketplace |
| Local files and terminal | No | Workspace file tools; opt-in approved argv execution | No dedicated OS sandbox or remote execution backend |
| Durable sessions and search | No | SQLite history; word-based session search; run exports | No cross-provider migration or advanced retrieval |
| Persistent memory | No | Approved notes and word-based recall | No semantic/vector memory or automatic memory consolidation |
| Reusable skills | No | Bundled and custom Markdown procedures; approval on agent saves | No Hermes skill marketplace, full Agent Skills directory format, or automatic evaluated skill evolution |
| Scheduled tasks | No | Persistent interval schedules and approval-aware runs | No cron/calendar expressions, time-zone rules, or chat delivery |
| Control surface | Chat proxy | Dashboard, CLI, authenticated REST, Open WebUI adapter | No Telegram, Discord, Slack, WhatsApp, email or other messaging gateways |
| Web research | No | Public text fetch; optional SearXNG search | No interactive browser automation or signed-in sessions |
| Model backends | Ollama chat | Ollama chat plus native tool-capable agent model | No multi-provider inference router for agent runs |
| Human approvals | Advice only | Immutable proposals, approve/deny/cancel, file hash check, consumed approvals | Single operator; no users, roles or approval routing |
| Extensions/MCP | No | Not included | No MCP server/client integration |
| Learning from runs | No | Operator can save procedures; agent may propose approved skill saves | No automated training, evaluation or self-improvement loop |

The practical advancement is that Skylinee can now perform observable work and persist the result across sessions. Real usefulness depends on a capable local model and the quality of supplied evidence. A workflow test with the demo backend proves orchestration, not model intelligence.

Ollama implementation reference: [native tool calling](https://docs.ollama.com/capabilities/tool-calling). Skylinee submits `/api/chat` tools, preserves the assistant tool-call message, appends each tool result, and asks the model for its next step. It checks `/api/show` capabilities before running.
