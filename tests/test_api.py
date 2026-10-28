import time

import httpx
import pytest
from fastapi.testclient import TestClient

from skylinee_harness.config import get_settings
from skylinee_harness.demo import app as demo
from skylinee_harness.main import app

KEY = "test-key-which-is-over-24-characters-long"
AUTH = {"Authorization": "Bearer " + KEY}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKYLINEE_API_KEY", KEY)
    monkeypatch.setenv("SKYLINEE_OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("SKYLINEE_SCHEDULER_POLL_SECONDS", ".1")
    get_settings.cache_clear()
    original = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        return original(*args, **kwargs, transport=httpx.ASGITransport(app=demo))

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def await_status(client, ident, statuses):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        r = client.get("/v1/agent/runs/" + ident, headers=AUTH).json()
        if r["status"] in statuses:
            return r
        time.sleep(0.025)
    pytest.fail(f"Run did not reach {statuses}: {r}")


def test_dashboard_public_but_api_authenticated(client):
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/healthz").status_code == 200
    assert client.get("/v1/agent/sessions").status_code == 401
    assert (
        client.get(
            "/v1/agent/sessions", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert client.get("/v1/models", headers=AUTH).status_code == 200


def test_empty_key_fails_closed(client, monkeypatch):
    monkeypatch.setenv("SKYLINEE_API_KEY", "")
    get_settings.cache_clear()
    assert client.get("/v1/agent/sessions").status_code == 503


def test_native_ollama_loop_through_http_adapter(client):
    doctor = client.get("/v1/agent/doctor", headers=AUTH).json()
    assert doctor["tools_supported"] and doctor["demo_backend"]
    r = client.post("/v1/agent/runs", headers=AUTH, json={"prompt": "Calculate demo"})
    assert r.status_code == 202
    done = await_status(client, r.json()["id"], {"completed", "failed"})
    assert done["status"] == "completed" and "42" in done["answer"]
    assert "messages" not in done
    transcript = client.get(
        "/v1/agent/runs/" + done["id"] + "/export", headers=AUTH
    ).json()["transcript"]
    assert [m["role"] for m in transcript] == ["user", "assistant", "tool", "assistant"]


def test_approval_http_flow_and_persistence(client):
    r = client.post(
        "/v1/agent/runs", headers=AUTH, json={"prompt": "Write demo report"}
    ).json()
    await_status(client, r["id"], {"waiting_approval"})
    a = client.get("/v1/agent/approvals", headers=AUTH).json()[0]
    assert not (app.state.settings.workspace_dir / "demo-report.txt").exists()
    assert (
        client.post(
            "/v1/agent/approvals/" + a["id"], headers=AUTH, json={"decision": "approve"}
        ).status_code
        == 200
    )
    done = await_status(client, r["id"], {"completed", "failed"})
    assert done["status"] == "completed"
    assert (
        (app.state.settings.workspace_dir / "demo-report.txt")
        .read_text()
        .startswith("Skylinee")
    )
    assert (
        client.post(
            "/v1/agent/approvals/" + a["id"], headers=AUTH, json={"decision": "approve"}
        ).status_code
        == 400
    )
    assert (
        client.get("/v1/agent/sessions/" + done["session_id"], headers=AUTH).json()[
            "messages"
        ][-1]["role"]
        == "assistant"
    )


def test_memory_skill_schedule_crud(client):
    m = client.post(
        "/v1/agent/memories", headers=AUTH, json={"text": "Corey prefers evidence."}
    )
    assert m.status_code == 201
    assert (
        client.get("/v1/agent/memories", headers=AUTH).json()[0]["text"]
        == "Corey prefers evidence."
    )
    assert (
        client.delete("/v1/agent/memories/" + m.json()["id"], headers=AUTH).status_code
        == 200
    )
    assert (
        client.post(
            "/v1/agent/skills",
            headers=AUTH,
            json={"name": "my-review", "content": "Inspect and summarize."},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v1/agent/skills",
            headers=AUTH,
            json={"name": "research", "content": "Overwrite bundled"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/v1/agent/schedules",
            headers=AUTH,
            json={"name": "Daily", "prompt": "Review", "interval_seconds": 5},
        ).status_code
        == 422
    )
    s = client.post(
        "/v1/agent/schedules",
        headers=AUTH,
        json={
            "name": "Daily",
            "prompt": "Review",
            "interval_seconds": 86400,
            "skill": "my-review",
        },
    )
    assert s.status_code == 201
    assert (
        client.delete("/v1/agent/schedules/" + s.json()["id"], headers=AUTH).status_code
        == 200
    )


def test_invalid_and_missing_resources(client):
    assert client.get("/v1/agent/runs/missing", headers=AUTH).status_code == 404
    assert (
        client.post(
            "/v1/agent/runs", headers=AUTH, json={"prompt": "", "extra": True}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/chat/completions", headers=AUTH, json={"messages": [42]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/chat/completions", headers=AUTH, json={"messages": []}
        ).status_code
        == 422
    )


def test_openwebui_agent_completion(client):
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "skylinee-agent",
            "messages": [{"role": "user", "content": "Calculate demo"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert (
        body["skylinee"]["status"] == "completed"
        and "42" in body["choices"][0]["message"]["content"]
    )


def test_openwebui_agent_pending_approval_returns_run_id(client):
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "skylinee-agent",
            "messages": [{"role": "user", "content": "write demo"}],
        },
    )
    body = response.json()
    assert body["skylinee"]["status"] == "waiting_approval"
    assert body["skylinee"]["run_id"] in body["choices"][0]["message"]["content"]


def test_openwebui_agent_buffered_sse(client):
    r = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "skylinee-agent",
            "stream": True,
            "messages": [{"role": "user", "content": "calculate demo"}],
        },
    )
    assert r.status_code == 200 and "text/event-stream" in r.headers["content-type"]
    assert "42" in r.text and "[DONE]" in r.text


def test_legacy_gateway_still_routes_without_tools(client):
    payload = {
        "model": "skylinee-auto",
        "messages": [{"role": "user", "content": "hello"}],
    }
    response = client.post("/v1/chat/completions", headers=AUTH, json=payload)
    assert (
        response.status_code == 200
        and response.headers["x-skylinee-route"] == "general"
    )
    payload["stream"] = True
    assert (
        "[DONE]" in client.post("/v1/chat/completions", headers=AUTH, json=payload).text
    )
    payload["tools"] = [{"type": "function", "function": {"name": "bad"}}]
    assert (
        client.post("/v1/chat/completions", headers=AUTH, json=payload).status_code
        == 403
    )


def test_second_server_cannot_use_same_state(client):
    with pytest.raises(RuntimeError, match="already in use"):
        with TestClient(app):
            pass
    assert client.get("/v1/agent/sessions", headers=AUTH).status_code == 200
