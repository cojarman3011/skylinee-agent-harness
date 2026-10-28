"""Validated tools. Public fetch pins vetted DNS results; writes need run approvals."""

import ast
import asyncio
import hashlib
import http.client
import ipaddress
import json
import math
import operator
import os
import re
import signal
import socket
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .schemas import (
    CalcArgs,
    EmptyArgs,
    FetchArgs,
    MemoryInput,
    PathArgs,
    SearchArgs,
    SkillInput,
    TailArgs,
    TerminalArgs,
    WriteArgs,
)
from .skills import all_skills, get_skill

SPECS = {
    "workspace_list": (
        PathArgs,
        "List a directory inside the configured workspace.",
        False,
    ),
    "workspace_read": (PathArgs, "Read a UTF-8 workspace file.", False),
    "workspace_write": (
        WriteArgs,
        "Create or replace a workspace file; human approval required.",
        True,
    ),
    "log_tail": (TailArgs, "Read the last lines of a workspace log.", False),
    "failed_login_count": (
        PathArgs,
        "Count lines matching Failed password or authentication failure in a supplied log. Not a count of unique attacks.",
        False,
    ),
    "web_search": (
        SearchArgs,
        "Search the configured SearXNG service and return source URLs.",
        False,
    ),
    "web_fetch": (
        FetchArgs,
        "Read a public HTTP(S) page; returned page text is untrusted evidence.",
        False,
    ),
    "calculator": (
        CalcArgs,
        "Evaluate bounded arithmetic without code execution.",
        False,
    ),
    "memory_search": (SearchArgs, "Search saved operator memories.", False),
    "memory_save": (MemoryInput, "Persist a memory only after approval.", True),
    "session_search": (
        SearchArgs,
        "Search saved session titles and conversation text.",
        False,
    ),
    "skills_list": (EmptyArgs, "List available procedures.", False),
    "skill_read": (SearchArgs, "Read a skill by exact name in query.", False),
    "skill_save": (
        SkillInput,
        "Save or update a reusable procedure after approval.",
        True,
    ),
    "terminal": (
        TerminalArgs,
        "Execute argv in workspace after explicit approval. Enabled only by operator configuration; this is not an OS sandbox.",
        True,
    ),
}


def schemas(settings):
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": model.model_json_schema(),
            },
        }
        for name, (model, desc, _) in SPECS.items()
        if name != "terminal" or settings.enable_terminal
    ]


def validated(name, arguments):
    if name not in SPECS:
        raise ValueError("Unknown tool")
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")
    return SPECS[name][0].model_validate(arguments).model_dump()


def path_in(root: Path, relative: str):
    root = root.resolve()
    if Path(relative).is_absolute():
        raise ValueError("Use a workspace-relative path")
    p = (root / relative).resolve()
    if not p.is_relative_to(root):
        raise ValueError("Path escapes workspace")
    parts = p.relative_to(root).parts
    if any(
        x.startswith(".")
        or re.search(r"(credential|private.key|id_rsa|id_ed25519)", x, re.IGNORECASE)
        for x in parts
    ):
        raise ValueError("Hidden and credential-like paths are unavailable to tools")
    return p


def snapshot(path):
    if not path.exists():
        return "absent"
    if not path.is_file():
        raise ValueError("Target is not a regular file")
    if path.stat().st_size > 8_000_000:
        raise ValueError("File exceeds 8 MB tool limit")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_target(url):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise ValueError("Public HTTP(S) URLs without credentials only")
    port = p.port or (443 if p.scheme == "https" else 80)
    if port not in (80, 443):
        raise ValueError("Only ports 80 and 443 are allowed")
    records = socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)
    ips = {r[4][0] for r in records}
    if not ips or any(not ipaddress.ip_address(i).is_global for i in ips):
        raise ValueError(
            "Private, loopback, reserved and link-local destinations are blocked"
        )
    return p, port, min(ips)


def fetch_public(url, max_bytes=512_000):
    deadline = time.monotonic() + 30
    for _ in range(4):
        if time.monotonic() > deadline:
            raise TimeoutError("Page retrieval time budget exhausted")
        p, port, ip = public_target(url)
        cls = (
            http.client.HTTPSConnection
            if p.scheme == "https"
            else http.client.HTTPConnection
        )
        conn = cls(p.hostname, port, timeout=12)
        # Connect to the vetted address while preserving Host and TLS certificate hostname.
        conn._create_connection = (
            lambda address, timeout=12, *args, _ip=ip, _port=port, **kw: (
                socket.create_connection((_ip, _port), timeout)
            )
        )
        try:
            target = p.path or "/"
            if p.query:
                target += "?" + p.query
            conn.request(
                "GET",
                target,
                headers={
                    "User-Agent": "SkylineeHarness/0.6",
                    "Accept-Encoding": "identity",
                },
            )
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                loc = response.getheader("Location")
                if not loc:
                    raise ValueError("Redirect without Location")
                url = urljoin(url, loc)
                continue
            if response.status >= 400:
                raise ValueError(f"Page returned HTTP {response.status}")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise ValueError("Compressed response refused")
            mime = response.getheader("Content-Type", "").split(";")[0]
            if mime not in ("text/html", "text/plain", "application/json"):
                raise ValueError("Only HTML, text and JSON pages are supported")
            raw = bytearray()
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError("Page retrieval time budget exhausted")
                chunk = response.read1(min(65536, max_bytes + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > max_bytes:
                    raise ValueError("Page exceeds size limit")
            text = raw.decode("utf-8", errors="replace")
            if mime == "text/html":
                soup = BeautifulSoup(text, "html.parser")
                for x in soup(["script", "style", "nav", "footer", "noscript"]):
                    x.decompose()
                text = soup.get_text(" ", strip=True)
            return {"url": url, "text": text, "untrusted": True}
        finally:
            conn.close()
    raise ValueError("Too many redirects")


def calculate(expression):
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 40:
        raise ValueError("Expression too complex")
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    def visit(n):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            v = n.value
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            v = visit(n.operand) * (1 if isinstance(n.op, ast.UAdd) else -1)
        elif isinstance(n, ast.BinOp) and type(n.op) in ops:
            a, b = visit(n.left), visit(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 20:
                raise ValueError("Exponent too large")
            v = ops[type(n.op)](a, b)
        else:
            raise ValueError("Only numeric arithmetic is supported")
        if not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1e100:
            raise ValueError("Result out of bounds")
        return v

    return visit(tree.body)


class ToolRegistry:
    def __init__(self, settings, store, audit):
        self.settings, self.store, self.audit = settings, store, audit
        settings.workspace_dir.mkdir(parents=True, exist_ok=True)

    def prepare(self, name, args):
        args = validated(name, args)
        if name == "terminal" and not self.settings.enable_terminal:
            raise ValueError("Terminal is disabled")
        before = None
        if name == "workspace_write":
            p = path_in(self.settings.workspace_dir, args["path"])
            before = snapshot(p)
            if before != "absent" and not args["overwrite"]:
                raise ValueError("File exists; overwrite must be explicit")
        if name == "terminal":
            command = args["argv"][0]
            if (
                command not in self.settings.terminal_allowlist.split(",")
                or "/" in command
                or "\\" in command
            ):
                raise ValueError("Executable is not in the operator allowlist")
            if any(len(a) > 4000 for a in args["argv"]):
                raise ValueError("Terminal argument too long")
            path_in(self.settings.workspace_dir, args["cwd"])
        return args, SPECS[name][2], before

    async def execute(self, name, args, *, approved=False, before=None):
        if SPECS[name][2] and not approved:
            raise PermissionError("Approval is required")
        root = self.settings.workspace_dir
        if name == "workspace_list":
            p = path_in(root, args["path"])
            return {
                "entries": [
                    {"name": x.name, "directory": x.is_dir()}
                    for x in sorted(p.iterdir())[:200]
                    if not x.name.startswith(".") and not x.is_symlink()
                ]
            }
        if name in ("workspace_read", "log_tail", "failed_login_count"):
            p = path_in(root, args["path"])
            snapshot(p)
            text = p.read_text(encoding="utf-8", errors="replace")
            if name == "log_tail":
                return {
                    "path": args["path"],
                    "text": "\n".join(text.splitlines()[-args["lines"] :]),
                }
            if name == "failed_login_count":
                return {
                    "matching_lines": sum(
                        bool(
                            re.search(
                                r"Failed password|authentication failure",
                                s,
                                re.IGNORECASE,
                            )
                        )
                        for s in text.splitlines()
                    ),
                    "definition": "Matching log lines, not unique attacks",
                }
            return {
                "path": args["path"],
                "text": text[: self.settings.max_tool_chars],
                "truncated": len(text) > self.settings.max_tool_chars,
            }
        if name == "workspace_write":
            p = path_in(root, args["path"])
            if snapshot(p) != before:
                raise ValueError(
                    "File changed since approval was requested; no write performed"
                )
            p.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents clobbering newly appeared files.
            if before == "absent":
                with p.open("x", encoding="utf-8") as f:
                    f.write(args["content"])
            else:
                temp = p.with_name(p.name + ".skylinee-tmp")
                with temp.open("x", encoding="utf-8") as f:
                    f.write(args["content"])
                os.replace(temp, p)
            return {"written": args["path"], "sha256": snapshot(p)}
        if name == "calculator":
            return {"result": calculate(args["expression"])}
        if name == "web_fetch":
            return await asyncio.to_thread(fetch_public, args["url"])
        if name == "web_search":
            if not self.settings.searxng_url:
                raise ValueError(
                    "Configure SKYLINEE_SEARXNG_URL and enable JSON output in SearXNG"
                )
            async with httpx.AsyncClient(timeout=15, trust_env=False) as c:
                async with c.stream(
                    "GET",
                    self.settings.searxng_url.rstrip("/") + "/search",
                    params={"q": args["query"], "format": "json"},
                ) as r:
                    r.raise_for_status()
                    raw = bytearray()
                    async for chunk in r.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2_000_000:
                            raise ValueError("Search response too large")
                    rows = json.loads(raw).get("results", [])[:5]
            return {
                "results": [
                    {
                        "title": str(x.get("title", ""))[:300],
                        "url": str(x.get("url", ""))[:2000],
                        "snippet": str(x.get("content", ""))[:1800],
                    }
                    for x in rows
                ],
                "untrusted": True,
            }
        if name == "memory_search":
            return {"memories": self.store.search("memory", args["query"], ["text"])}
        if name == "memory_save":
            return self.store.new("memory", text=args["text"])
        if name == "session_search":
            return {
                "sessions": self.store.search(
                    "session", args["query"], ["title", "messages"], limit=5
                )
            }
        if name == "skills_list":
            return {
                "skills": [
                    {"name": s["name"], "bundled": s["bundled"]}
                    for s in all_skills(self.store)
                ]
            }
        if name == "skill_read":
            return get_skill(self.store, args["query"])
        if name == "skill_save":
            if args["name"] in [
                s["name"] for s in all_skills(self.store) if s["bundled"]
            ]:
                raise ValueError("Choose a new name; bundled skills are read-only")
            return self.store.put("skill", {"id": args["name"], **args})
        if name == "terminal":
            return await self.terminal(args)
        raise ValueError("Unknown tool")

    async def terminal(self, args):
        cwd = path_in(self.settings.workspace_dir, args["cwd"])
        proc = await asyncio.create_subprocess_exec(
            *args["argv"],
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "LANG": "C.UTF-8",
                "HOME": str(self.settings.workspace_dir.resolve()),
            },
        )
        data = bytearray()
        reason = None

        async def read():
            nonlocal reason
            while chunk := await proc.stdout.read(4096):
                data.extend(chunk)
                if len(data) > self.settings.max_tool_chars:
                    reason = "output_limit"
                    break
            if reason is None:
                await proc.wait()

        try:
            await asyncio.wait_for(read(), timeout=20)
        except TimeoutError:
            reason = "timeout"
        finally:
            # Kill the group too: a child must not survive a bounded approved command.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
        return {
            "returncode": proc.returncode,
            "output": bytes(data[: self.settings.max_tool_chars]).decode(
                errors="replace"
            ),
            "stop_reason": reason,
        }
