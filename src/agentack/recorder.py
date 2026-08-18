from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TextIO

from .canonical import action_hash
from .models import Action, TraceEvent


class Recorder:
    """Small instrumentation helper for emitting AgentAck JSONL traces."""

    def __init__(self, path: str | Path, session_id: str, *, append: bool = False) -> None:
        self.path = Path(path)
        self.session_id = session_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: TextIO = self.path.open("a" if append else "w", encoding="utf-8", newline="\n")

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _write(self, event: TraceEvent) -> None:
        self._handle.write(json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        self._handle.write("\n")
        self._handle.flush()

    def propose(self, action_id: str, action: Action, *, intent_id: str | None = None) -> str:
        self._write(
            TraceEvent(
                type="action_proposed",
                timestamp=self._now(),
                session_id=self.session_id,
                action_id=action_id,
                intent_id=intent_id,
                action=action,
            )
        )
        return action_hash(action)

    def request_approval(self, approval_id: str, action_id: str, *, intent_id: str | None = None) -> None:
        self._write(
            TraceEvent(
                type="approval_requested",
                timestamp=self._now(),
                session_id=self.session_id,
                approval_id=approval_id,
                action_id=action_id,
                intent_id=intent_id,
            )
        )

    def decide(
        self,
        approval_id: str,
        action_id: str,
        decision: str,
        *,
        approved_action: Action | None = None,
        intent_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        if decision not in {"allow", "deny"}:
            raise ValueError("decision must be 'allow' or 'deny'")
        timestamp = self._now()
        self._write(
            TraceEvent(
                type="approval_decision",
                timestamp=timestamp,
                session_id=self.session_id,
                approval_id=approval_id,
                action_id=action_id,
                intent_id=intent_id,
                decision=decision,  # type: ignore[arg-type]
                approved_action_hash=action_hash(approved_action) if approved_action is not None else None,
                expires_at=(timestamp + timedelta(seconds=ttl_seconds)) if ttl_seconds is not None else None,
            )
        )

    def execute(
        self,
        action_id: str,
        action: Action,
        *,
        approval_id: str | None = None,
        intent_id: str | None = None,
    ) -> None:
        self._write(
            TraceEvent(
                type="action_executed",
                timestamp=self._now(),
                session_id=self.session_id,
                action_id=action_id,
                approval_id=approval_id,
                intent_id=intent_id,
                action=action,
            )
        )

    def interrupt(self, *, reason: str | None = None) -> None:
        self._write(
            TraceEvent(
                type="interrupt",
                timestamp=self._now(),
                session_id=self.session_id,
                reason=reason,
            )
        )
