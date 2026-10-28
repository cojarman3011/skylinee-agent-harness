import pytest

from skylinee_harness.policy import PolicyViolation, enforce_advisory_policy


def test_injects_advisory_system_message() -> None:
    payload = {
        "model": "skylinee-auto",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    wrapped = enforce_advisory_policy(payload)
    assert wrapped["messages"][0]["role"] == "system"
    assert "advisory-only" in wrapped["messages"][0]["content"]
    assert payload["messages"][0]["role"] == "user"


def test_rejects_tool_execution_in_v01() -> None:
    payload = {
        "messages": [{"role": "user", "content": "Run it"}],
        "tools": [{"type": "function", "function": {"name": "delete_file"}}],
    }
    with pytest.raises(PolicyViolation):
        enforce_advisory_policy(payload)
