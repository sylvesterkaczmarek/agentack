from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import action_hash, canonicalize_action
from .models import Action, ActionIdentity, ActionLifecycleIdentity, TRACE_SCHEMA_VERSION, TraceEvent
from .policy import Policy

REPORT_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    return str(uuid.uuid4())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def policy_sha256(policy: Policy) -> str:
    payload = {
        "version": 1,
        "approval": {
            "require_for": sorted(policy.require_approval_for),
            "max_age_seconds": policy.max_approval_age_seconds,
            "single_use": policy.approval_single_use,
            "exact_action_binding": policy.require_exact_action_binding,
            "stop_is_terminal": policy.stop_is_terminal,
        },
    }
    return canonical_json_sha256(payload)


def trace_digest_from_events(events: Iterable[TraceEvent]) -> str:
    digest = hashlib.sha256()
    for event in events:
        encoded = json.dumps(
            event.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        digest.update(encoded)
        digest.update(b"\n")
    return digest.hexdigest()


def action_identity(action: Action | None) -> ActionIdentity | None:
    if action is None:
        return None
    canonical = canonicalize_action(action)
    return ActionIdentity(
        sha256=action_hash(action),
        tool=canonical.tool,
        operation=canonical.operation,
    )


def trace_action_identities(events: Iterable[TraceEvent]) -> list[ActionLifecycleIdentity]:
    ordered: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    for event in events:
        if not event.action_id:
            continue
        if event.action_id not in records:
            ordered.append(event.action_id)
            records[event.action_id] = {
                "action_id": event.action_id,
                "intent_id": event.intent_id,
                "approval_id": event.approval_id,
                "decision": None,
                "expected": None,
                "presented": None,
                "executed": None,
                "blocked": False,
            }
        current = records[event.action_id]
        if current["intent_id"] is None and event.intent_id is not None:
            current["intent_id"] = event.intent_id
        if current["approval_id"] is None and event.approval_id is not None:
            current["approval_id"] = event.approval_id
        if event.type == "action_proposed":
            current["expected"] = action_identity(event.action)
        elif event.type == "approval_requested":
            current["presented"] = action_identity(event.action)
        elif event.type == "approval_decision":
            current["decision"] = event.decision
        elif event.type == "action_executed":
            current["executed"] = action_identity(event.action)
        elif event.type == "action_blocked":
            current["blocked"] = True
    return [ActionLifecycleIdentity(**records[action_id]) for action_id in ordered]


def safe_source_name(source: str | Path | None) -> str | None:
    if source is None:
        return None
    return Path(source).name


def base_provenance(
    *,
    agentack_version: str,
    kind: str,
    session_id: str | None,
    run_id: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "producer": {"name": "AgentAck", "version": agentack_version},
        "run": {
            "run_id": run_id or new_run_id(),
            "kind": kind,
            "evaluated_at": evaluated_at or utc_now_iso(),
            "session_id": session_id,
        },
    }


def trace_input_provenance(
    *,
    trace_sha256: str,
    policy: Policy,
    trace_source: str | Path | None,
    policy_source: str | Path | None,
) -> dict[str, Any]:
    return {
        "trace": {
            "schema_version": TRACE_SCHEMA_VERSION,
            "sha256": trace_sha256,
            "source": safe_source_name(trace_source),
        },
        "policy": {
            "schema_version": 1,
            "sha256": policy_sha256(policy),
            "source": safe_source_name(policy_source) if policy_source else "default",
        },
        "evidence": None,
    }


def adapter_input_provenance(evidence_sha256: str | None) -> dict[str, Any]:
    return {
        "trace": None,
        "policy": None,
        "evidence": {"sha256": evidence_sha256} if evidence_sha256 else None,
    }
