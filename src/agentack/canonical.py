from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import Action

_TOOL_ALIASES = {
    "bash": "shell",
    "sh": "shell",
    "terminal": "shell",
    "command": "shell",
    "execute-command": "shell",
    "powershell": "shell",
    "pwsh": "shell",
    "cmd": "shell",
    "file": "filesystem",
    "fs": "filesystem",
    "http": "network",
    "https": "network",
    "web": "network",
    "model-context-protocol": "mcp",
    "mcp-tool": "mcp",
}

_OPERATION_ALIASES: dict[str, dict[str, str]] = {
    "shell": {
        "exec": "run",
        "execute": "run",
        "command": "run",
        "invoke": "run",
    },
    "filesystem": {
        "remove": "delete",
        "rm": "delete",
        "unlink": "delete",
        "write-file": "write",
        "read-file": "read",
    },
    "network": {
        "fetch": "request",
        "http-request": "request",
    },
    "mcp": {
        "invoke": "call",
        "execute": "call",
    },
}


def _token(value: str) -> str:
    return "-".join(value.strip().lower().replace("_", "-").split())


def canonicalize_action(action: Action) -> Action:
    """Return a deterministic action identity using an explicit alias map."""
    tool_token = _token(action.tool)
    tool = _TOOL_ALIASES.get(tool_token, tool_token)
    operation_token = _token(action.operation)
    operation = _OPERATION_ALIASES.get(tool, {}).get(operation_token, operation_token)
    return Action(
        tool=tool,
        operation=operation,
        resource=action.resource,
        parameters=action.parameters,
    )


def canonical_action_key(action: Action) -> str:
    normalized = canonicalize_action(action)
    return f"{normalized.tool}:{normalized.operation}"


def canonical_json(value: Any) -> str:
    """Serialize JSON data deterministically for security-relevant identity."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def action_hash(action: Action) -> str:
    payload = canonical_json(canonicalize_action(action).to_dict()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
