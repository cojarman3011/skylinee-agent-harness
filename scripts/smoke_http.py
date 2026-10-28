"""Run actual HTTP servers, CLI, restart persistence, and optional dashboard DOM check.

Uses a temporary directory and deterministic demo backend, not a real LLM.
Run from the project with: python scripts/smoke_http.py [--dom]
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    backend_port, app_port = port(), port()
    base = f"http://127.0.0.1:{app_port}"
    processes = []
    with tempfile.TemporaryDirectory(prefix="skylinee-smoke-") as tmp:
        cwd = Path(tmp)
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        # Do not let the caller's settings override isolated smoke-test settings.
        env = {k: v for k, v in env.items() if not k.startswith("SKYLINEE_")}
        env["SKYLINEE_SCHEDULER_POLL_SECONDS"] = "0.1"
        log = (cwd / "servers.log").open("w+")

        def start(module, server_port):
            p = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    module,
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(server_port),
                ],
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=log,
            )
            processes.append(p)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    r = httpx.get(
                        f"http://127.0.0.1:{server_port}"
                        + ("/api/tags" if "demo" in module else "/healthz"),
                        timeout=1,
                        trust_env=False,
                    )
                    if r.status_code == 200:
                        return p
                except httpx.HTTPError:
                    pass
                if p.poll() is not None:
                    break
                time.sleep(0.05)
            raise RuntimeError("Server did not start")

        def stop(p):
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()

        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "skylinee_harness.cli",
                    "init",
                    "--ollama",
                    f"http://127.0.0.1:{backend_port}",
                    "--model",
                    "skylinee-demo",
                ],
                cwd=cwd,
                env=env,
                check=True,
                capture_output=True,
            )
            key = next(
                x.split("=", 1)[1]
                for x in (cwd / ".env").read_text().splitlines()
                if x.startswith("SKYLINEE_API_KEY=")
            )
            start("skylinee_harness.demo:app", backend_port)
            server = start("skylinee_harness.main:app", app_port)
            with httpx.Client(
                base_url=base,
                headers={"Authorization": "Bearer " + key},
                trust_env=False,
                timeout=20,
            ) as c:

                def call(path, method="GET", data=None):
                    r = c.request(method, "/v1/agent" + path, json=data)
                    r.raise_for_status()
                    return r.json()

                def wait(ident, wanted):
                    end = time.monotonic() + 10
                    while time.monotonic() < end:
                        r = call("/runs/" + ident)
                        if r["status"] in wanted:
                            return r
                        if r["status"] in ("failed", "cancelled", "step_limit"):
                            raise RuntimeError(str(r))
                        time.sleep(0.05)
                    raise RuntimeError("Run timed out")

                assert c.get("/").status_code == 200
                assert call("/doctor")["demo_backend"]
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "skylinee_harness.cli",
                        "--url",
                        base,
                        "ask",
                        "calculate demo",
                    ],
                    cwd=cwd,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                assert json.loads(result.stdout)["status"] == "completed"
                run = call("/runs", "POST", {"prompt": "write demo report"})
                wait(run["id"], {"waiting_approval"})
                assert not (cwd / "workspace/demo-report.txt").exists()
                approval = next(
                    a for a in call("/approvals") if a["run_id"] == run["id"]
                )
                call("/memories", "POST", {"text": "Persist across restart."})
                stop(server)
                server = start("skylinee_harness.main:app", app_port)
                assert call("/memories")[0]["text"] == "Persist across restart."
                assert call("/runs/" + run["id"])["status"] == "waiting_approval"
                call("/approvals/" + approval["id"], "POST", {"decision": "approve"})
                wait(run["id"], {"completed"})
                assert (
                    (cwd / "workspace/demo-report.txt")
                    .read_text()
                    .startswith("Skylinee approval")
                )
                denied = call("/runs", "POST", {"prompt": "remember demo"})
                wait(denied["id"], {"waiting_approval"})
                approval = next(
                    a for a in call("/approvals") if a["run_id"] == denied["id"]
                )
                count = len(call("/memories"))
                call("/approvals/" + approval["id"], "POST", {"decision": "deny"})
                wait(denied["id"], {"completed"})
                assert len(call("/memories")) == count
                print(
                    "Live HTTP smoke passed: CLI, native tool loop, no write before approval, restart persistence, approved write, denied memory."
                )
                if "--dom" in sys.argv:
                    subprocess.run(
                        ["node", str(ROOT / "scripts/smoke_dashboard.cjs")],
                        cwd=cwd,
                        env={**env, "SMOKE_BASE": base},
                        check=True,
                        timeout=90,
                    )
        except Exception:
            log.flush()
            print((cwd / "servers.log").read_text(), file=sys.stderr)
            raise
        finally:
            for p in reversed(processes):
                if p.poll() is None:
                    stop(p)
            log.close()


if __name__ == "__main__":
    main()
