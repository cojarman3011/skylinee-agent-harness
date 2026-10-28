# Operations, permissions, and recovery

## Trust boundary

This is a single-operator service. Anyone with its bearer key can read all sessions, tool results, memories and pending proposals, approve changes, and create schedules. There is no per-user separation. The root dashboard, static assets, health endpoint, and schema docs are public; data APIs require a non-placeholder key of at least 24 characters. The browser retains the key in tab memory, not local storage or cookies.

Keep the default localhost bind. For remote access, use your private network or an authenticated TLS reverse proxy. Plain HTTP sends the bearer key without transport encryption. Rotate the key by changing `.env` and restarting. Do not put `.env` in the workspace or source control. Public page text, logs, memory and skills are not treated as authorization. Prompt-injection instructions are also included in the model system message; those instructions cannot guarantee model behavior, so actual writes are enforced by server approvals.

Built-in file tools reject paths outside the workspace, hidden path components, and credential-like names. They cap file reads at 8 MB. A write proposal captures the current file hash (or absence); execution rechecks it. Avoid concurrent untrusted filesystem writers: these application checks are not an OS security boundary against hostile local processes or filesystem races.

Public web fetch resolves and validates all returned IPs, connects to a selected public IP while preserving the hostname for TLS, revalidates each redirect, permits only HTTP/HTTPS ports 80/443, rejects compressed responses, and reads at most 512 KB of supported text. There is no automatic ingestion of remote tools or arbitrary scripts. Web fetch is read-only but still sends requests to public sites. SearXNG is an operator-trusted service URL; configure it carefully. Search results are capped and marked untrusted.

## Data

`data/state.sqlite3` contains full session messages, prompts, tool results, proposal arguments, memories, skills, schedules and run events. State persists even when `SKYLINEE_LOG_PROMPT_CONTENT=false`; that setting applies only to the JSONL audit log. Treat state and exports as sensitive. SQLite files are not encrypted by this application. There is no automatic retention or erasure policy.

The audit log records event metadata and request hashes for routed chats by default. It is not a tamper-proof audit ledger. The browser and CLI expose recent lists; word search scans up to the latest 2,000 entries. Tool output, conversation history, run duration, model turns and terminal processes have budgets. Limits are designed for a personal local agent rather than a high-throughput service.

Back up by stopping the service, copying the complete data directory/volume and workspace, then restarting. Include SQLite's WAL/SHM files if present; do not copy only the main database while it is being written. Keep `.env` separately with appropriate permissions. To move between native and Docker installs, stop both and migrate state explicitly; their default volumes are different.

## State transitions

A new task is `queued`, then `running`. A tool requiring permission moves it to `waiting_approval`. A decision resumes that exact run; approved arguments are the saved proposal, not a regenerated request. Denial is passed to the model as a denied result. Tool errors are passed back as errors; the model can explain them or choose a different valid step.

Normal completion saves a final answer and appends a user/answer pair to session history. Failed, cancelled and incomplete runs retain their evidence in the run export, but do not append an incomplete answer to session history. The agent can search completed session text. Only one active run is allowed per session; two runs can execute concurrently across sessions.

A consumed approval cannot be used again. There is no claim of exactly-once execution across a power failure: an action may complete before the final state is persisted. At startup, a run left `running` becomes `interrupted`, and an approval left `executing` becomes `uncertain`. Neither is automatically replayed. Inspect the actual file or effect and event history, then start a fresh task if appropriate. A saved pending approval remains pending after restart. A queued approved action that has not begun may resume.

Cancelling stops the run and any active bounded terminal process group. It cannot undo a write or other completed effect. During graceful server shutdown active runs are cancelled; queued and waiting runs remain persisted. A schedule's pending run prevents overlapping repeats of that schedule.

## Troubleshooting

| Symptom | Action |
|---|---|
| 503 key setup error | Run `skylinee init` or configure a random key of at least 24 characters; placeholders are rejected |
| 401 | Use the current key from the same server's `.env` |
| Model check fails | Verify the URL, reachability and installed model name; run `ollama list` on the Ollama machine |
| Model lacks tools | Select a model that reports `tools` in `/api/show`; the small legacy code model is not automatically reused |
| Agent loops or chooses poor tools | Use a stronger tool-capable model, specific evidence and a clear procedure; inspect exported tool results |
| Web search unconfigured | Set a reachable SearXNG URL with JSON format enabled, or use direct public URLs |
| Approval no longer pending | Inspect the current run; decisions cannot be submitted twice |
| File changed since proposal | Read the current file and request a new proposal |
| Data directory already in use | Stop the other server or select a separate data directory; never launch multiple Uvicorn workers |
| Docker cannot reach host Ollama | Use `host.docker.internal` with the supplied host mapping or the Ollama machine's LAN URL |
| Schedule does not run with browser closed | The browser can close, but the server process must remain running |
