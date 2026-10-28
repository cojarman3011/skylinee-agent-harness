# Changelog

## 0.6.0 — October 15, 2026

- Added an Ollama native agent loop and the `skylinee-agent` Open WebUI alias.
- Added workspace, log, arithmetic, public web, memory, session and skill tools; terminal is opt-in.
- Added persisted sessions, searchable notes, custom Markdown skills, four bundled procedures and run exports.
- Added an approval queue with exact proposal review, file hash checks, consumed decisions, cancellation and conservative interruption recovery.
- Added persistent interval schedules that wait on outstanding approvals rather than accumulating duplicate runs.
- Added a browser dashboard, CLI, setup launcher, deterministic demo backend, HTTP/DOM smoke checks and regression suite.
- Retained the original advisory routing aliases and streaming gateway.
- Changed empty/placeholder API key handling to deny data API access until configured.
- Changed Docker storage defaults to named persistent data/workspace volumes and a non-root service account.

The archive had no numbered 3–6 roadmap. This release defines those stages as tools, persistence, skills, and scheduling/control, respectively. It does not implement the full Hermes feature set.
