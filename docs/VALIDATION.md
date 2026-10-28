# Validation — Skylinee 0.6.0

Tested October 15, 2026 in a Linux x86-64 container, Python 3.12. No access to Corey's machine or live Ollama inference was used.

| Check | Actual result |
|---|---|
| Automated suite: `python3 -m pytest -q` | 67 tests passed. One upstream Starlette/TestClient deprecation warning; no test failures. |
| Real HTTP + CLI: `python3 scripts/smoke_http.py` | Passed against separate Uvicorn application and demo-backend subprocesses. Native `/api/chat` tool loop, no file write before approval, restart with pending approval, persisted memory, approved write and denied memory all verified. |
| Dashboard behavior: `python3 scripts/smoke_http.py --dom` with jsdom | Passed: authenticated connect, model check, calculation, proposal display, approval, memory save, skill save, schedule create/delete and tabs. Uses the real dashboard JavaScript and live HTTP endpoints. |
| JavaScript syntax: `node --check src/skylinee_harness/static/app.js` | Passed. |
| Python source checks: Ruff E4/E7/E9/F/I | Passed. Ruff formatting applied. |
| Distribution build: `python3 -m build --no-isolation` | Source distribution and Python wheel built successfully. |
| Wheel contents and clean install | Static HTML, CSS and JavaScript included. Installed the built wheel into a separate virtual environment; runtime import, server startup, dashboard assets and authenticated bundled skills passed. |
| Actual browser rendering | Not verified. Chromium was not installed; its download returned an unusable response. DOM checks do not establish visual layout, browser compatibility or responsive rendering. |
| Actual Ollama/model quality | Not verified. The deterministic demo validates orchestration and protocol handling, not model reasoning or real-model tool selection. |
| Docker build/run | Not verified; Docker was unavailable. Compose YAML and volume paths inspected. |
| SearXNG public search | Adapter tested with mocked HTTP responses; no live search instance configured. |
| Public web retrieval | URL restrictions, private-IP blocking and redirect revalidation tested with controlled DNS/HTTP fixtures; no live web retrieval benchmark. |

## Suite coverage

The suite covers the original routing/advisory behavior and new API authentication, JSON validation, model capability checks, native Ollama adapter, multiple tool results, sessions, memory, custom skills, interval schedule claims, pending-run suppression, cancellation, failure and step budgets. Approval tests cover no action before decision, denial, consumed approval reuse, exact saved proposal execution, file hash changes and interrupted/uncertain recovery. Tool tests cover workspace traversal and escaping symlinks, read/output limits, credential-like paths, calculator code rejection, public URL restrictions, redirects, disabled terminal, argv restrictions and secret environment isolation.

## Repeat the checks

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/smoke_http.py
python -m pip install build
python -m build
```

The optional DOM check requires Node.js 20+ and jsdom installed separately. For example:

```bash
npm install --prefix /tmp/skylinee-dom jsdom
NODE_PATH=/tmp/skylinee-dom/node_modules python scripts/smoke_http.py --dom
```

Smoke scripts use temporary state, randomly generated keys and ephemeral localhost ports, then stop their test servers. They do not connect to or modify the configured production Ollama server. The demo identifies itself in the model check and every response.

## Deployment acceptance

Before using real tasks, start the release on the intended host, configure its actual Ollama URL and installed tool-capable model, and run the model check. Then repeat the arithmetic, synthetic-log and approved-file-write examples from the README with the real model. Confirm results and response time on your hardware. This deployment acceptance remains outstanding; it cannot be inferred from demo tests.
