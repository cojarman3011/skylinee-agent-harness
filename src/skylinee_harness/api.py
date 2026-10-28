import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .schemas import (
    ApprovalInput,
    MemoryInput,
    RunInput,
    ScheduleInput,
    SessionInput,
    SkillInput,
)
from .skills import all_skills, get_skill


def build_router(auth):
    router = APIRouter(prefix="/v1/agent", dependencies=[Depends(auth)])

    @router.get("/status")
    async def agent_status(request: Request):
        s = request.app.state.settings
        return {
            "agent_model": s.model_agent,
            "terminal_enabled": s.enable_terminal,
            "search_configured": bool(s.searxng_url),
            "max_steps": s.max_agent_steps,
            "privacy": "Single-operator service. Sessions, tool results, memories and proposals persist in the data volume.",
        }

    @router.get("/doctor")
    async def doctor(request: Request):
        try:
            return await request.app.state.engine.doctor()
        except Exception as e:
            raise HTTPException(
                502,
                f"Backend check failed: {type(e).__name__}. Verify Ollama URL and installed agent model.",
            ) from e

    @router.get("/sessions")
    async def sessions(request: Request):
        return [
            {k: v for k, v in s.items() if k != "messages"}
            for s in request.app.state.store.list("session")
        ]

    @router.post("/sessions", status_code=201)
    async def new_session(data: SessionInput, request: Request):
        return request.app.state.engine.session(data.title)

    @router.get("/sessions/{ident}")
    async def session(ident: str, request: Request):
        return request.app.state.store.get("session", ident)

    @router.get("/runs")
    async def runs(request: Request):
        return [public_run(r) for r in request.app.state.store.list("run")]

    @router.post("/runs", status_code=202)
    async def start(data: RunInput, request: Request):
        return public_run(request.app.state.engine.create_run(**data.model_dump()))

    @router.get("/runs/{ident}")
    async def run(ident: str, request: Request):
        return public_run(request.app.state.store.get("run", ident))

    @router.post("/runs/{ident}/cancel")
    async def cancel(ident: str, request: Request):
        return public_run(request.app.state.engine.cancel(ident))

    @router.get("/runs/{ident}/export")
    async def export(ident: str, request: Request):
        run = request.app.state.store.get("run", ident)
        return {**public_run(run), "transcript": run["messages"][1:]}

    @router.get("/approvals")
    async def approvals(request: Request):
        return request.app.state.store.list("approval", None)

    @router.post("/approvals/{ident}")
    async def decide(ident: str, data: ApprovalInput, request: Request):
        return request.app.state.engine.decide(ident, data.decision)

    @router.get("/memories")
    async def memories(request: Request):
        return request.app.state.store.list("memory")

    @router.post("/memories", status_code=201)
    async def memory(data: MemoryInput, request: Request):
        return request.app.state.store.new("memory", **data.model_dump())

    @router.delete("/memories/{ident}")
    async def delete_memory(ident: str, request: Request):
        request.app.state.store.get("memory", ident)
        request.app.state.store.remove("memory", ident)
        return {"deleted": ident}

    @router.get("/skills")
    async def skills(request: Request):
        return all_skills(request.app.state.store)

    @router.post("/skills", status_code=201)
    async def skill(data: SkillInput, request: Request):
        store = request.app.state.store
        if any(s["name"] == data.name and s["bundled"] for s in all_skills(store)):
            raise ValueError("Bundled skills are read-only")
        return store.put("skill", {"id": data.name, **data.model_dump()})

    @router.get("/schedules")
    async def schedules(request: Request):
        return request.app.state.store.list("schedule")

    @router.post("/schedules", status_code=201)
    async def schedule(data: ScheduleInput, request: Request):
        if data.skill:
            get_skill(request.app.state.store, data.skill)
        return request.app.state.store.new(
            "schedule",
            **data.model_dump(),
            next_run=time.time() + data.interval_seconds,
        )

    @router.delete("/schedules/{ident}")
    async def delete_schedule(ident: str, request: Request):
        request.app.state.store.get("schedule", ident)
        request.app.state.store.remove("schedule", ident)
        return {
            "deleted": ident,
            "note": "Existing runs remain; cancel them separately if desired.",
        }

    return router


def public_run(run):
    return {
        k: v for k, v in run.items() if k not in ("messages", "pending_calls", "cursor")
    }
