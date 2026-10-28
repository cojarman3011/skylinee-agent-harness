from skylinee_harness.config import Settings
from skylinee_harness.router import route_request


def settings() -> Settings:
    return Settings(
        model_general="general-model",
        model_code="code-model",
        model_security="security-model",
    )


def test_routes_security_prompt() -> None:
    result = route_request(
        "skylinee-auto",
        [{"role": "user", "content": "Summarize this Sysmon security alert."}],
        settings(),
    )
    assert result.category == "security"
    assert result.model == "security-model"


def test_routes_code_prompt() -> None:
    result = route_request(
        "skylinee-auto",
        [{"role": "user", "content": "Debug this Python function."}],
        settings(),
    )
    assert result.category == "code"
    assert result.model == "code-model"


def test_routes_general_prompt() -> None:
    result = route_request(
        "skylinee-auto",
        [{"role": "user", "content": "Draft a meeting agenda."}],
        settings(),
    )
    assert result.category == "general"


def test_explicit_alias_beats_keywords() -> None:
    result = route_request(
        "skylinee-general",
        [{"role": "user", "content": "Write Python code."}],
        settings(),
    )
    assert result.category == "general"
