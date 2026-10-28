"""Deterministic Ollama-shaped test backend. No language model or real reasoning."""

import json

from fastapi import FastAPI

app = FastAPI(title="Skylinee deterministic demo backend — NOT a language model")


@app.get("/api/tags")
async def tags():
    return {"models": [{"name": "skylinee-demo"}]}


@app.post("/api/show")
async def show():
    return {"capabilities": ["completion", "tools"], "skylinee_demo": True}


@app.post("/api/chat")
async def chat(body: dict):
    messages = body["messages"]
    last = messages[-1]
    if last["role"] == "tool":
        result = {
            "role": "assistant",
            "content": "DEMO tool result (deterministic workflow check): "
            + last["content"],
        }
    else:
        prompt = last.get("content", "").lower()
        if "write" in prompt:
            name, args = (
                "workspace_write",
                {
                    "path": "demo-report.txt",
                    "content": "Skylinee approval workflow verified.\n",
                    "overwrite": True,
                },
            )
        elif "remember" in prompt:
            name, args = (
                "memory_save",
                {
                    "text": "Demo preference: summarize operational evidence before proposing changes."
                },
            )
        elif "log" in prompt:
            name, args = "failed_login_count", {"path": "auth.log"}
        else:
            name, args = "calculator", {"expression": "(3+4)*6"}
        result = {
            "role": "assistant",
            "content": "DEMO: requesting " + name,
            "tool_calls": [{"function": {"name": name, "arguments": args}}],
        }
    return {"model": "skylinee-demo", "message": result, "done": True}


@app.post("/v1/chat/completions")
async def proxy_chat(body: dict):
    from fastapi.responses import StreamingResponse

    text = "DEMO chat gateway response. This backend does not run a language model."
    if body.get("stream"):
        chunk = {
            "id": "demo",
            "object": "chat.completion.chunk",
            "choices": [
                {"index": 0, "delta": {"content": text}, "finish_reason": None}
            ],
        }

        async def events():
            yield "data: " + json.dumps(chunk) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")
    return {
        "id": "demo",
        "object": "chat.completion",
        "model": body.get("model"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
    }
