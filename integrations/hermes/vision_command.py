"""Recognize /vision in the OpenAI bridge; retain native Hermes tool authority."""
import re
from copy import deepcopy

COMMAND = re.compile(r'^/vision(?:\s|$)', re.IGNORECASE)
INSTRUCTION = (
    'The latest user invoked /vision. Load the installed vision skill with skill_view '
    'and follow it, using the native terminal tool and its existing approvals. '
    'Run the bundled detection helper against the configured Skylinee Vision AI service. '
    'Use the actual user image or attachment path; never fabricate an image path or '
    'detections. If the skill, service or accessible image is missing, report that '
    'specific blocker. Do not substitute web search or model-only guessing for detection.'
)


def prepare_vision_command(payload):
    messages = payload.get('messages', [])
    latest = next((m for m in reversed(messages) if m.get('role') == 'user'), None)
    if latest is None:
        return payload
    content = latest.get('content', '')
    text = content if isinstance(content, str) else '\n'.join(
        p.get('text', '') for p in content
        if isinstance(p, dict) and p.get('type') == 'text'
    ) if isinstance(content, list) else ''
    if not COMMAND.match(text.lstrip()):
        return payload
    result = deepcopy(payload)
    result['messages'].insert(0, {'role': 'system', 'content': INSTRUCTION})
    return result
