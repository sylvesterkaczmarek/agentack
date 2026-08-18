from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .models import Action

DEFAULT_PATTERNS = (
    "shell:*",
    "filesystem:write",
    "filesystem:delete",
    "network:*",
    "mcp:*",
    "deploy:*",
    "credential:*",
    "process:*",
)


@dataclass(frozen=True)
class Policy:
    require_approval_for: tuple[str, ...] = DEFAULT_PATTERNS
    max_approval_age_seconds: int = 300
    approval_single_use: bool = True
    require_exact_action_binding: bool = True
    stop_is_terminal: bool = True

    def requires_approval(self, action: Action) -> bool:
        key = f"{action.tool}:{action.operation}"
        return any(fnmatch.fnmatchcase(key, pattern) for pattern in self.require_approval_for)

    @classmethod
    def from_toml(cls, path: str | Path) -> "Policy":
        with Path(path).open("rb") as handle:
            data = tomllib.load(handle)
        if data.get("version") != 1:
            raise ValueError("policy version must be 1")
        approval = data.get("approval", {})
        if not isinstance(approval, dict):
            raise ValueError("[approval] must be a TOML table")
        patterns = approval.get("require_for", list(DEFAULT_PATTERNS))
        if not isinstance(patterns, list) or not all(isinstance(item, str) and item for item in patterns):
            raise ValueError("approval.require_for must be a list of non-empty strings")
        max_age = approval.get("max_age_seconds", 300)
        if not isinstance(max_age, int) or isinstance(max_age, bool) or max_age <= 0 or max_age > 86400:
            raise ValueError("approval.max_age_seconds must be an integer from 1 to 86400")
        single_use = approval.get("single_use", True)
        exact_binding = approval.get("exact_action_binding", True)
        stop_is_terminal = approval.get("stop_is_terminal", True)
        for name, value in (
            ("approval.single_use", single_use),
            ("approval.exact_action_binding", exact_binding),
            ("approval.stop_is_terminal", stop_is_terminal),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be boolean")
        return cls(
            require_approval_for=tuple(patterns),
            max_approval_age_seconds=max_age,
            approval_single_use=single_use,
            require_exact_action_binding=exact_binding,
            stop_is_terminal=stop_is_terminal,
        )

    def to_toml(self) -> str:
        patterns = ",\n  ".join(f'"{item}"' for item in self.require_approval_for)
        return (
            "version = 1\n\n"
            "[approval]\n"
            f"max_age_seconds = {self.max_approval_age_seconds}\n"
            f"single_use = {str(self.approval_single_use).lower()}\n"
            f"exact_action_binding = {str(self.require_exact_action_binding).lower()}\n"
            f"stop_is_terminal = {str(self.stop_is_terminal).lower()}\n"
            "require_for = [\n  " + patterns + "\n]\n"
        )
