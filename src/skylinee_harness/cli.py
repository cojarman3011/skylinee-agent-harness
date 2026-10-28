"""Small authenticated client and local server launcher (Linux/macOS)."""

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

import httpx

from .config import get_settings


def main():
    p = argparse.ArgumentParser(prog="skylinee")
    p.add_argument(
        "--url", default=os.getenv("SKYLINEE_SERVER_URL", "http://127.0.0.1:8000")
    )
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser(
        "init",
        help="Create .env and local directories without replacing existing settings",
    )
    init.add_argument("--ollama", default="http://127.0.0.1:11434")
    init.add_argument("--model", default="qwen3:4b")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("doctor")
    ask = sub.add_parser("ask")
    ask.add_argument("prompt")
    ask.add_argument("--skill")
    ask.add_argument("--session")
    ask.add_argument("--wait", type=int, default=330)
    sub.add_parser("runs")
    show = sub.add_parser("show")
    show.add_argument("id")
    sub.add_parser("approvals")
    for name in ("approve", "deny", "cancel"):
        a = sub.add_parser(name)
        a.add_argument("id")
    sub.add_parser("skills")
    imp = sub.add_parser("import-skill")
    imp.add_argument("name")
    imp.add_argument("file", type=Path)
    sub.add_parser("memories")
    mem = sub.add_parser("remember")
    mem.add_argument("text")
    sched = sub.add_parser("schedule")
    sched.add_argument("name")
    sched.add_argument("prompt")
    sched.add_argument(
        "--every", type=int, default=86400, help="Interval in seconds, minimum 60"
    )
    sched.add_argument("--skill")
    sub.add_parser("schedules")
    rem = sub.add_parser("unschedule")
    rem.add_argument("id")
    args = p.parse_args()
    try:
        if args.command == "init":
            for value in (args.ollama, args.model):
                if any(c in value for c in "\r\n\x00"):
                    raise ValueError("Configuration values must be single-line")
            path = Path(".env")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(
                    "SKYLINEE_API_KEY="
                    + secrets.token_urlsafe(36)
                    + "\nSKYLINEE_OLLAMA_BASE_URL="
                    + args.ollama
                    + "\nSKYLINEE_MODEL_AGENT="
                    + args.model
                    + "\nSKYLINEE_DATA_DIR=data\nSKYLINEE_WORKSPACE_DIR=workspace\nSKYLINEE_AUDIT_LOG_PATH=data/audit.jsonl\nSKYLINEE_ENABLE_TERMINAL=false\n"
                )
            Path("data").mkdir(exist_ok=True)
            Path("workspace").mkdir(exist_ok=True)
            print(
                "Created .env (mode 600), data/, workspace/. Copy your API key from .env into the dashboard."
            )
            return
        if args.command == "serve":
            import uvicorn

            uvicorn.run(
                "skylinee_harness.main:app", host=args.host, port=args.port, workers=1
            )
            return
        settings = get_settings()
        if not settings.api_key:
            raise ValueError(
                "Missing API key; run skylinee init in your project directory"
            )
        with httpx.Client(
            base_url=args.url.rstrip("/") + "/v1/agent",
            headers={"Authorization": "Bearer " + settings.api_key},
            timeout=30,
            trust_env=False,
        ) as c:

            def call(path, method="GET", body=None):
                r = c.request(method, path, json=body)
                r.raise_for_status()
                return r.json()

            cmd = args.command
            if cmd == "ask":
                result = call(
                    "/runs",
                    "POST",
                    {
                        "prompt": args.prompt,
                        "session_id": args.session,
                        "skill": args.skill,
                    },
                )
                deadline = time.monotonic() + args.wait
                while (
                    result["status"] in ("queued", "running")
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.5)
                    result = call("/runs/" + result["id"])
            elif cmd in ("approve", "deny"):
                result = call(
                    "/approvals/" + args.id,
                    "POST",
                    {"decision": "approve" if cmd == "approve" else "deny"},
                )
            elif cmd == "cancel":
                result = call("/runs/" + args.id + "/cancel", "POST")
            elif cmd == "show":
                result = call("/runs/" + args.id + "/export")
            elif cmd == "import-skill":
                result = call(
                    "/skills",
                    "POST",
                    {"name": args.name, "content": args.file.read_text()},
                )
            elif cmd == "remember":
                result = call("/memories", "POST", {"text": args.text})
            elif cmd == "schedule":
                result = call(
                    "/schedules",
                    "POST",
                    {
                        "name": args.name,
                        "prompt": args.prompt,
                        "interval_seconds": args.every,
                        "skill": args.skill,
                    },
                )
            elif cmd == "unschedule":
                result = call("/schedules/" + args.id, "DELETE")
            else:
                result = call("/" + cmd)
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except (httpx.HTTPError, ValueError, OSError) as e:
        print(f"Skylinee: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
