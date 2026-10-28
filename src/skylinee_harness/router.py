from dataclasses import dataclass
from typing import Any

from .config import Settings

CODE_TERMS = {
    "bug",
    "code",
    "debug",
    "dockerfile",
    "function",
    "javascript",
    "python",
    "refactor",
    "repository",
    "script",
    "sql",
    "typescript",
}

SECURITY_TERMS = {
    "alert",
    "cve",
    "defender",
    "event log",
    "fail2ban",
    "firewall",
    "incident",
    "malware",
    "network traffic",
    "phishing",
    "security",
    "soc",
    "sysmon",
    "threat",
    "vulnerability",
    "wireshark",
}


@dataclass(frozen=True)
class RouteDecision:
    category: str
    model: str
    reason: str


def _message_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
    return "\n".join(parts).lower()


def route_request(
    requested_model: str,
    messages: list[dict[str, Any]],
    settings: Settings,
) -> RouteDecision:
    aliases = {
        "skylinee-general": "general",
        "skylinee-code": "code",
        "skylinee-security": "security",
    }
    if requested_model in aliases:
        category = aliases[requested_model]
        return RouteDecision(
            category, settings.model_map[category], "explicit route alias"
        )

    for category, configured_model in settings.model_map.items():
        if requested_model == configured_model:
            return RouteDecision(
                category, configured_model, "explicit configured model"
            )

    text = _message_text(messages)
    security_score = sum(term in text for term in SECURITY_TERMS)
    code_score = sum(term in text for term in CODE_TERMS)

    if security_score > 0 and security_score >= code_score:
        return RouteDecision(
            "security", settings.model_security, "security terms detected"
        )
    if code_score > 0:
        return RouteDecision("code", settings.model_code, "coding terms detected")
    return RouteDecision("general", settings.model_general, "default route")
