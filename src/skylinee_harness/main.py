import asyncio
import fcntl
import json
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .agent import AgentEngine
from .api import build_router
from .audit import AuditLogger
from .config import Settings, get_settings
from .policy import PolicyViolation, enforce_advisory_policy
from .router import RouteDecision, route_request
from .store import Store


def require_api_key(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if len(settings.api_key) < 24 or settings.api_key.lower().startswith(
        ("change", "replace")
    ):
        raise HTTPException(
            status_code=503,
            detail="Set a unique SKYLINEE_API_KEY of at least 24 characters; run skylinee init",
        )
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key"
        )
    supplied = authorization[len(prefix) :]
    if not secrets.compare_digest(supplied, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.audit = AuditLogger(settings.audit_log_path, settings.log_prompt_content)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    lock = (settings.data_dir / "instance.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError(
            "This data directory is already in use. Run exactly one server worker."
        )
    store = Store(settings.data_dir / "state.sqlite3")
    app.state.store = store
    app.state.engine = AgentEngine(settings, store, app.state.audit)
    app.state.engine.recover()
    worker = asyncio.create_task(app.state.engine.worker())
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await app.state.engine.stop()
        store.close()
        lock.close()


app = FastAPI(
    title="Skylinee Agent Harness",
    version=__version__,
    description="Local agent with tools, approvals, persistent sessions, skills and scheduling.",
    lifespan=lifespan,
)
app.include_router(build_router(require_api_key))
STATIC = Path(__file__).parent / "static"
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")


@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(STATIC / "index.html")


@app.exception_handler(KeyError)
async def missing(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Item not found"})


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)[:500]})


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/v1/models", dependencies=[Depends(require_api_key)])
async def list_models(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    names = [
        "skylinee-agent",
        "skylinee-auto",
        "skylinee-general",
        "skylinee-code",
        "skylinee-security",
    ]
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "created": 0, "owned_by": "skylinee"}
            for name in names
        ],
    }


@app.post("/v1/routes/preview", dependencies=[Depends(require_api_key)])
async def preview_route(
    request: Request, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    payload = await _read_chat_payload(request)
    decision = route_request(
        payload.get("model", "skylinee-auto"), payload["messages"], settings
    )
    return {
        "requested_model": payload.get("model", "skylinee-auto"),
        "category": decision.category,
        "selected_model": decision.model,
        "reason": decision.reason,
    }


@app.post("/v1/chat/completions", dependencies=[Depends(require_api_key)])
async def chat_completions(
    request: Request, settings: Settings = Depends(get_settings)
):
    original_payload = await _read_chat_payload(request)
    if original_payload.get("model") == "skylinee-agent":
        return await agent_completion(request, original_payload)
    request_id = f"skylinee-{uuid.uuid4()}"
    started = time.monotonic()

    decision = route_request(
        original_payload.get("model", "skylinee-auto"),
        original_payload["messages"],
        settings,
    )
    try:
        payload = enforce_advisory_policy(original_payload)
    except PolicyViolation as exc:
        _audit(
            request, request_id, decision, started, "policy_denied", original_payload
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc

    payload["model"] = decision.model
    upstream_url = f"{settings.ollama_base_url.rstrip('/')}/v1/chat/completions"

    if payload.get("stream", False):
        return await _stream_response(
            request,
            upstream_url,
            payload,
            original_payload,
            request_id,
            decision,
            started,
            settings,
        )
    return await _json_response(
        request,
        upstream_url,
        payload,
        original_payload,
        request_id,
        decision,
        started,
        settings,
    )


async def _read_chat_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="Request body must be valid JSON"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise HTTPException(status_code=422, detail="messages must be an array")
    if not 1 <= len(payload["messages"]) <= 100:
        raise HTTPException(422, "Supply 1 to 100 messages")
    if any(
        not isinstance(m, dict)
        or m.get("role") not in ("system", "user", "assistant", "tool")
        or not isinstance(m.get("content"), str)
        for m in payload["messages"]
    ):
        raise HTTPException(422, "Each message requires a valid role and text content")
    if sum(len(m["content"]) for m in payload["messages"]) > 100000:
        raise HTTPException(413, "Conversation exceeds 100,000 characters")
    return payload


async def agent_completion(request, payload):
    if payload.get("tools") or payload.get("functions"):
        raise HTTPException(
            400, "Agent tools are server-managed; use the dashboard for approvals"
        )
    history = [m for m in payload["messages"] if m["role"] in ("user", "assistant")]
    if not history or history[-1]["role"] != "user":
        raise HTTPException(422, "Last conversation message must be a user prompt")
    if len(history[-1]["content"]) > 24000:
        raise HTTPException(413, "Agent prompt exceeds 24,000 characters")
    engine = request.app.state.engine
    session = engine.session(history[-1]["content"][:80])
    session["messages"] = history[:-1]
    engine.store.put("session", session)
    run = engine.create_run(history[-1]["content"], session_id=session["id"])

    async def wait_result():
        while True:
            current = engine.store.get("run", run["id"])
            if current["status"] not in ("queued", "running"):
                text = (
                    current["answer"]
                    or current["error"]
                    or f"Action needs approval in the Skylinee dashboard. Run: {run['id']}"
                )
                return current, text
            if await request.is_disconnected():
                return current, f"Run continues in dashboard: {run['id']}"
            await asyncio.sleep(0.2)

    def chunk(text, finish=None):
        return {
            "id": run["id"],
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "skylinee-agent",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": text} if text else {},
                    "finish_reason": finish,
                }
            ],
        }

    if payload.get("stream"):

        async def stream():
            pending = asyncio.create_task(wait_result())
            try:
                while not pending.done():
                    done, _ = await asyncio.wait({pending}, timeout=5)
                    if not done:
                        yield b": skylinee run in progress\n\n"
                _, text = await pending
                yield ("data: " + json.dumps(chunk(text)) + "\n\n").encode()
                yield (
                    "data: " + json.dumps(chunk("", "stop")) + "\n\ndata: [DONE]\n\n"
                ).encode()
            finally:
                if not pending.done():
                    pending.cancel()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"X-Skylinee-Run-ID": run["id"]},
        )
    current, text = await wait_result()
    return JSONResponse(
        {
            "id": run["id"],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "skylinee-agent",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "skylinee": {"run_id": run["id"], "status": current["status"]},
        },
        headers={"X-Skylinee-Run-ID": run["id"]},
    )


async def _json_response(
    request: Request,
    upstream_url: str,
    payload: dict[str, Any],
    original_payload: dict[str, Any],
    request_id: str,
    decision: RouteDecision,
    started: float,
    settings: Settings,
) -> JSONResponse:
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds
        ) as client:
            response = await client.post(upstream_url, json=payload)
            response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        _audit(
            request,
            request_id,
            decision,
            started,
            "upstream_error",
            original_payload,
            str(exc),
        )
        raise HTTPException(
            status_code=502, detail=f"Ollama request failed: {exc}"
        ) from exc

    _audit(request, request_id, decision, started, "completed", original_payload)
    return JSONResponse(
        content=body,
        headers={
            "X-Skylinee-Request-ID": request_id,
            "X-Skylinee-Route": decision.category,
            "X-Skylinee-Model": decision.model,
        },
    )


async def _stream_response(
    request: Request,
    upstream_url: str,
    payload: dict[str, Any],
    original_payload: dict[str, Any],
    request_id: str,
    decision: RouteDecision,
    started: float,
    settings: Settings,
) -> StreamingResponse:
    client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    try:
        upstream = await client.send(
            client.build_request("POST", upstream_url, json=payload),
            stream=True,
        )
        upstream.raise_for_status()
    except httpx.HTTPError as exc:
        await client.aclose()
        _audit(
            request,
            request_id,
            decision,
            started,
            "upstream_error",
            original_payload,
            str(exc),
        )
        raise HTTPException(
            status_code=502, detail=f"Ollama request failed: {exc}"
        ) from exc

    async def iterator() -> AsyncIterator[bytes]:
        outcome = "completed"
        error: str | None = None
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        except Exception as exc:  # Streaming failures must still reach the audit trail.
            outcome = "stream_error"
            error = str(exc)
            raise
        finally:
            await upstream.aclose()
            await client.aclose()
            _audit(
                request, request_id, decision, started, outcome, original_payload, error
            )

    return StreamingResponse(
        iterator(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "text/event-stream"),
        headers={
            "X-Skylinee-Request-ID": request_id,
            "X-Skylinee-Route": decision.category,
            "X-Skylinee-Model": decision.model,
        },
    )


def _audit(
    request: Request,
    request_id: str,
    decision: RouteDecision,
    started: float,
    outcome: str,
    payload: dict[str, Any],
    error: str | None = None,
) -> None:
    event = {
        "request_id": request_id,
        "route": decision.category,
        "model": decision.model,
        "route_reason": decision.reason,
        "outcome": outcome,
        "latency_ms": round((time.monotonic() - started) * 1000, 2),
    }
    if error:
        event["error"] = error
    request.app.state.audit.write(event, payload)
