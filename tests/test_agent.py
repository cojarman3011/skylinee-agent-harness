import asyncio
import json
import time
import uuid

import pytest

from skylinee_harness.store import Store


def tool(name, args):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": uuid.uuid4().hex, "function": {"name": name, "arguments": args}}
        ],
    }


def finish(text="Verified."):
    return {"role": "assistant", "content": text}


def fake(engine, *responses):
    iterator = iter(responses)

    async def call(run):
        return next(iterator)

    engine.model_call = call


@pytest.mark.asyncio
async def test_read_tool_loop_and_session_history(engine):
    fake(engine, tool("calculator", {"expression": "6*7"}), finish("42"))
    r = engine.create_run("Calculate 6*7")
    await engine.drive(r["id"])
    r = engine.store.get("run", r["id"])
    assert r["status"] == "completed" and r["answer"] == "42" and r["steps"] == 2
    assert json.loads(r["messages"][-2]["content"])["result"] == 42
    next_run = engine.create_run("What was the result?", session_id=r["session_id"])
    assert next_run["messages"][-2] == {"role": "assistant", "content": "42"}


@pytest.mark.asyncio
async def test_approved_write_executes_once(engine):
    fake(
        engine,
        tool("workspace_write", {"path": "report.txt", "content": "Evidence."}),
        finish(),
    )
    r = engine.create_run("Write report")
    await engine.drive(r["id"])
    assert engine.store.get("run", r["id"])["status"] == "waiting_approval"
    assert not (engine.settings.workspace_dir / "report.txt").exists()
    approval = engine.store.list("approval")[0]
    engine.decide(approval["id"], "approve")
    await engine.drive(r["id"])
    assert (engine.settings.workspace_dir / "report.txt").read_text() == "Evidence."
    assert engine.store.get("approval", approval["id"])["status"] == "completed"
    with pytest.raises(ValueError):
        engine.decide(approval["id"], "approve")
    await engine.drive(r["id"])
    assert engine.store.get("run", r["id"])["steps"] == 2


@pytest.mark.asyncio
async def test_denied_action_never_writes(engine):
    fake(
        engine,
        tool("workspace_write", {"path": "denied.txt", "content": "x"}),
        finish("Denied."),
    )
    r = engine.create_run("Write")
    await engine.drive(r["id"])
    a = engine.store.list("approval")[0]
    engine.decide(a["id"], "deny")
    await engine.drive(r["id"])
    assert not (engine.settings.workspace_dir / "denied.txt").exists()
    assert any(
        e.get("outcome") == "denied" for e in engine.store.get("run", r["id"])["events"]
    )


@pytest.mark.asyncio
async def test_memory_and_skill_need_approval_then_persist(engine):
    fake(
        engine,
        tool("memory_save", {"text": "Prefer concise security summaries."}),
        tool(
            "skill_save",
            {"name": "review", "content": "Read evidence first. Then summarize."},
        ),
        finish(),
    )
    r = engine.create_run("Remember my procedure")
    await engine.drive(r["id"])
    assert engine.store.list("memory") == []
    engine.decide(engine.store.list("approval")[0]["id"], "approve")
    await engine.drive(r["id"])
    assert engine.store.list("memory")[0]["text"].startswith("Prefer")
    assert engine.store.list("skill") == []
    engine.decide(engine.store.list("approval")[0]["id"], "approve")
    await engine.drive(r["id"])
    other = Store(engine.settings.data_dir / "state.sqlite3")
    assert other.get("skill", "review")["content"].startswith("Read")
    other.close()
    new = engine.create_run("security summary", skill="review")
    assert (
        "Read evidence first" in new["messages"][0]["content"]
        and "Prefer concise" in new["messages"][0]["content"]
    )


@pytest.mark.asyncio
async def test_multiple_calls_all_return_results(engine):
    m = tool("calculator", {"expression": "1+1"})
    m["tool_calls"] += tool("calculator", {"expression": "2+2"})["tool_calls"]
    fake(engine, m, finish())
    r = engine.create_run("Calculate")
    await engine.drive(r["id"])
    r = engine.store.get("run", r["id"])
    assert len([m for m in r["messages"] if m["role"] == "tool"]) == 2


@pytest.mark.asyncio
async def test_step_budget(engine):
    engine.settings.max_agent_steps = 1
    fake(engine, tool("calculator", {"expression": "2+2"}))
    r = engine.create_run("Loop")
    await engine.drive(r["id"])
    assert engine.store.get("run", r["id"])["status"] == "step_limit"


@pytest.mark.asyncio
async def test_bad_tool_is_evidence_not_success(engine):
    fake(engine, tool("delete_everything", {}), finish("Tool failed."))
    r = engine.create_run("Bad tool")
    await engine.drive(r["id"])
    r = engine.store.get("run", r["id"])
    assert "error" in json.loads(r["messages"][-2]["content"])
    assert any(e.get("outcome") == "error" for e in r["events"])


@pytest.mark.asyncio
async def test_backend_failure_is_terminal(engine):
    async def fail(run):
        raise RuntimeError("offline")

    engine.model_call = fail
    r = engine.create_run("Hello")
    await engine.drive(r["id"])
    assert engine.store.get("run", r["id"])["status"] == "failed"


@pytest.mark.asyncio
async def test_unsupported_model_stops_before_tools(engine):
    async def doctor():
        return {"tools_supported": False}

    engine.doctor = doctor
    r = engine.create_run("Hello")
    await engine.drive(r["id"])
    assert "lacks tool support" in engine.store.get("run", r["id"])["error"]


def test_recovery_does_not_replay_uncertain_action(engine):
    r = engine.create_run("Write")
    r["status"] = "running"
    engine.store.put("run", r)
    a = engine.store.new(
        "approval",
        run_id=r["id"],
        call_id="x",
        tool="workspace_write",
        status="executing",
        decision="approve",
        arguments={},
        before=None,
    )
    engine.recover()
    assert engine.store.get("run", r["id"])["status"] == "interrupted"
    assert engine.store.get("approval", a["id"])["status"] == "uncertain"
    assert list(engine.settings.workspace_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_cancel_pending_approval(engine):
    fake(engine, tool("workspace_write", {"path": "x", "content": "x"}))
    r = engine.create_run("Write")
    await engine.drive(r["id"])
    a = engine.store.list("approval")[0]
    engine.cancel(r["id"])
    assert engine.store.get("approval", a["id"])["status"] == "cancelled"
    with pytest.raises(ValueError):
        engine.decide(a["id"], "approve")


@pytest.mark.asyncio
async def test_schedule_blocks_repetitions_while_pending(engine):
    fake(engine, tool("memory_save", {"text": "scheduled"}))
    s = engine.store.new(
        "schedule",
        name="test",
        prompt="Remember",
        skill=None,
        enabled=True,
        interval_seconds=60,
        next_run=time.time() - 1,
    )
    await engine.tick()
    await asyncio.gather(*engine.tasks.values())
    s = engine.store.get("schedule", s["id"])
    s["next_run"] = time.time() - 1
    engine.store.put("schedule", s)
    await engine.tick()
    assert (
        len(engine.store.list("run")) == 1 and len(engine.store.list("approval")) == 1
    )
    await engine.stop()


def test_due_claim_is_atomic_across_connections(engine):
    s = engine.store.new("schedule", enabled=True, interval_seconds=60, next_run=10)
    other = Store(engine.settings.data_dir / "state.sqlite3")
    assert engine.store.claim_schedule(s["id"], 20) is not None
    assert other.claim_schedule(s["id"], 20) is None
    other.close()


def test_one_active_run_per_session(engine):
    r = engine.create_run("One")
    with pytest.raises(ValueError):
        engine.create_run("Two", session_id=r["session_id"])
