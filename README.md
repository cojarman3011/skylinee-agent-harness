# Skylinee Agent Harness 0.6.0

Skylinee now runs an actual agent loop against Ollama: it can read evidence, call tools, request approval for changes, use saved memories and procedures, and perform scheduled work. It includes a browser dashboard, CLI, SQLite persistence, and an OpenAI-compatible connection for Open WebUI.

This release advances the uploaded 0.1 chat router through four implementation stages. The original archive did not define numbered steps 3–6, so this release uses the scope below. It implements a useful subset of Hermes-style workflows; it does not claim full Hermes feature or model-quality parity.

| Stage | Implemented | How to verify |
|---|---|---|
| 3 — Agent and tools | Native Ollama tool loop; workspace files; log analysis; arithmetic; public web fetch; optional SearXNG search; optional terminal | Run the calculator and log examples; inspect tool activity and exported transcript |
| 4 — Sessions and memory | SQLite session history, searchable conversations, saved memories, bounded context | Continue a session; restart and inspect history; search a saved note |
| 5 — Reusable skills | Four bundled Markdown procedures; custom skills from dashboard, CLI or approved agent proposal | Select `security-triage`; import a Markdown skill; reuse it on another task |
| 6 — Scheduling and control | Interval schedules, approval dashboard, approve/deny/cancel, run export, recovery handling, CLI and Open WebUI integration | Run an approval example; create a schedule; deny a proposed action |

## Start locally (Linux or macOS, Python 3.11+)

For a guided single-command launch, run `bash start.sh --ollama http://127.0.0.1:11434 --model qwen3:4b`. It creates a virtual environment, installs this package, creates `.env` if missing, and starts the local server. It does not install Ollama or download a model. Existing `.env` settings are retained. The explicit steps follow.

Extract the ZIP, open a terminal in this directory, then:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
skylinee init --ollama http://127.0.0.1:11434 --model qwen3:4b
```

`init` creates a unique key in `.env` and local `data/` and `workspace/` directories. It refuses to overwrite an existing `.env`. If upgrading from 0.1, retain your existing settings and add the new settings from `.env.example`; use a random key of at least 24 characters.

In your Ollama environment, install a model that supports native tool calling. The configured default is `qwen3:4b`; model quality and hardware requirements depend on your setup.

```bash
ollama pull qwen3:4b
skylinee serve
```

Open **http://127.0.0.1:8000**, paste `SKYLINEE_API_KEY` from `.env`, and select **Connect**, then **Check model**. The check must show `tools_supported: true`. The service refuses agent runs when the installed model does not advertise tools. Your old general/code models remain available for advisory routing; they are not used as the agent model.

For Corey's separate Ollama machine, use the address previously configured for that machine, if still correct:

```bash
skylinee init --ollama http://10.0.0.124:11434 --model qwen3:4b
```

If `.env` already exists, edit `SKYLINEE_OLLAMA_BASE_URL` there instead. The harness machine must be able to reach that server. No remote machine was modified as part of this release.

## First useful tasks

Copy the synthetic example log into the tool workspace:

```bash
cp examples/auth.log workspace/auth.log
skylinee doctor
skylinee ask "Calculate (3+4)*6 using the calculator."
skylinee ask "Read auth.log. Count failed login lines and explain what this count means." --skill security-triage
skylinee ask "Write a short incident summary to incident-summary.md. Use auth.log as evidence."
```

The third task should stop at `waiting_approval` before writing. In the dashboard, open **Approvals**, inspect the full path and content, then approve or deny. The agent resumes automatically. The dashboard shows its final response and event history. CLI equivalents:

```bash
skylinee approvals
skylinee approve APPROVAL_ID
skylinee show RUN_ID
# Or: skylinee deny APPROVAL_ID
```

A changed destination file invalidates its earlier write proposal. Approvals are consumed once; interrupted or uncertain actions are never automatically replayed. Inspect any uncertain action before retrying.

## Memory, skills, and recurring work

The dashboard's **Memory & skills** view saves notes and Markdown procedures. Direct operator saves are explicit actions; agent-generated saves require approval. Memory uses simple word matching, not embeddings. Session context includes recent complete user/answer pairs with a character budget.

```bash
skylinee remember "My preferred report format: findings, evidence, next action."
skylinee import-skill weekly-review examples/weekly-review.md
skylinee ask "Review auth.log and prepare a brief." --skill weekly-review
skylinee schedule "Daily log review" "Review auth.log and summarize failures." --every 86400 --skill security-triage
skylinee schedules
skylinee unschedule SCHEDULE_ID
```

Schedules are intervals measured from creation, not calendar/cron expressions. They run only while this server runs. After downtime, a due schedule creates one run and advances its due time; it does not replay every missed interval. Pending approvals block repeat runs of that schedule. Deleting a schedule does not cancel runs already created.

## Open WebUI

Keep your existing OpenAI-compatible connection, or add one:

- API URL: `http://HARNESS_HOST:8000/v1`
- API key: your `SKYLINEE_API_KEY`
- Agent model alias: **skylinee-agent**
- Advisory aliases: `skylinee-auto`, `skylinee-general`, `skylinee-code`, `skylinee-security`

Use `host.docker.internal` when Open WebUI is in Docker and Skylinee is on the host, with an appropriate host mapping on Linux. A remote container cannot reach a host service bound only to loopback; use a private network and deliberate bind address when required.

The agent alias buffers its final answer; it sends SSE keepalives rather than streaming model tokens. An approval request returns a run ID and dashboard instructions. Approve there and inspect the resumed result there or with `skylinee show RUN_ID`; Open WebUI's previous message does not update automatically. Regular advisory aliases retain upstream token streaming. The agent imports text user/assistant history from each request; it does not run caller-supplied tools or use caller system messages to override its tool policy. Attachments, images, function-tool compatibility and multimodal input are not supported.

## Optional web search

`web_fetch` can retrieve public text/HTML/JSON pages without a search service. It blocks private destinations, revalidates redirects, pins a vetted DNS address, and caps response size. It cannot access signed-in browser sessions or JavaScript-rendered pages.

To enable `web_search`, run your own SearXNG instance with JSON output enabled and set:

```dotenv
SKYLINEE_SEARXNG_URL=http://127.0.0.1:8080
```

See the [official SearXNG search API](https://docs.searxng.org/dev/search_api.html) for format configuration. The URL is an operator-controlled trusted service and may be private. No search service is bundled. An unconfigured search tool returns an explicit error; it never fabricates search results.

## Optional terminal

Terminal execution defaults to **off**. To enable it deliberately:

```dotenv
SKYLINEE_ENABLE_TERMINAL=true
SKYLINEE_TERMINAL_ALLOWLIST=python3,git,ls,pwd
```

Every command still needs explicit approval for the exact argument vector and working directory. There is no shell expansion, stdin, inherited application secret environment, or automatic tool permission. Commands have a 20-second runtime cap and an output cap; their process group is terminated on cancellation or limit. However, `python3` and `git` can perform broad actions. This is **not an operating-system sandbox**. An approved command can access files and network available to the server account, including persistent state if host permissions permit it. Prefer an isolated container without host credentials, privileged mounts, or the Docker socket. Workspace path restrictions protect built-in file tools, not arbitrary approved code.

## Docker

Create `.env` first with `skylinee init`. For Ollama on the host, change the URL to `http://host.docker.internal:11434`. For a separate Ollama machine, use its reachable LAN URL.

```bash
docker compose up --build -d
```

Compose binds the dashboard to localhost and uses persistent named volumes for `/data` and `/workspace`. These are separate from the native-install `data/` and `workspace/` directories. Copy an input file into the container with:

```bash
docker compose cp examples/auth.log skylinee-harness:/workspace/auth.log
```

The image runs as a non-root user; no extra Linux capabilities are granted. Run one server process and one worker per data directory. The process lock rejects a second instance using the same state. Native Windows is not supported by this release's process lock and process-group tools; use Linux/WSL or Docker.

## Test without Ollama

A clearly labeled deterministic demo backend exercises the real HTTP and approval workflow without downloading a model. It is a test fixture, not model inference.

In one terminal:

```bash
python -m uvicorn skylinee_harness.demo:app --host 127.0.0.1 --port 11439
```

In a fresh directory, with the same Python environment:

```bash
skylinee init --ollama http://127.0.0.1:11439 --model skylinee-demo
skylinee serve --port 8017
```

Open `http://127.0.0.1:8017`, connect with that directory's key, then try `calculate demo`, `write demo report`, or `remember demo`. “Write” always proposes `demo-report.txt`; it waits for approval. Demo responses and doctor output identify the backend as a demo. Switch to real Ollama for actual reasoning.

## Verification and boundaries

```bash
python -m pytest -q
python -m build --no-isolation
```

See [VALIDATION.md](docs/VALIDATION.md) for the checks actually run, [HERMES-COMPARISON.md](docs/HERMES-COMPARISON.md) for scope, and [OPERATIONS.md](docs/OPERATIONS.md) for persistence and recovery. The API reference is served at `/docs`; all agent API operations require the bearer key.

This release has been tested locally against a deterministic Ollama-shaped backend. It has not been installed on Corey's machine, benchmarked on a Raspberry Pi, or validated against a live Ollama model. Docker configuration is supplied, but building and running the container requires Docker, which was unavailable in the build environment. Reachable Ollama, an installed tool-capable model, and a successful model check are the remaining deployment requirements.
