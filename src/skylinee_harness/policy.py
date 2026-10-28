from typing import Any

ADVISORY_SYSTEM_MESSAGE = """You are operating through Skylinee Agent Harness in advisory-only mode.
Do not claim that you executed commands, changed accounts, modified firewalls, deleted files, or altered systems.
For consequential actions, explain the proposed action, its expected effect, and what a human should verify before approval.
Security analysis is allowed, but all containment or remediation steps require human authorization and execution."""


class PolicyViolation(ValueError):
    pass


def enforce_advisory_policy(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a policy-wrapped copy of an OpenAI chat payload.

    Routing aliases remain advisory. The skylinee-agent alias uses the
    separate server-managed tool loop and approval queue.
    """
    if payload.get("tools") or payload.get("functions"):
        raise PolicyViolation(
            "Routing aliases are advisory. Select skylinee-agent for server-managed tools."
        )

    wrapped = dict(payload)
    messages = list(payload.get("messages") or [])
    wrapped["messages"] = [
        {"role": "system", "content": ADVISORY_SYSTEM_MESSAGE},
        *messages,
    ]
    wrapped.pop("tool_choice", None)
    return wrapped
