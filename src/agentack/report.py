from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import __version__
from .adapters.base import AdapterTestResult
from .findings import RULES
from .models import EvaluationReport, Finding, TraceEvent
from .policy import Policy
from .provenance import (
    adapter_input_provenance,
    base_provenance,
    trace_action_identities,
    trace_input_provenance,
)


def render_text(report: EvaluationReport) -> str:
    lines = [f"AgentAck  {report.status}"]
    if report.source:
        lines.append(f"Trace: {report.source}")
    lines.append(f"Events: {report.events}")
    lines.append(f"Findings: {len(report.findings)}")
    if not report.findings:
        lines.append("")
        lines.append("Approval-integrity evidence is complete and no enabled rule failed.")
        return "\n".join(lines)
    lines.append("")
    for finding in report.findings:
        location = f" line {finding.line}" if finding.line is not None else ""
        spec = RULES[finding.rule_id]
        lines.append(f"{finding.severity.upper():8} {finding.rule_id} {finding.title}{location}")
        lines.append(f"  Evidence: {finding.message}")
        lines.append(f"  Why:      {spec.description}")
        lines.append(f"  Next:     {spec.remediation}")
    if report.status == "INCOMPLETE":
        lines.append("")
        lines.append("Result is INCOMPLETE because the trace lacks evidence required to establish approval integrity.")
    return "\n".join(lines)


def _finding_payload(finding: Finding) -> dict[str, Any]:
    spec = RULES[finding.rule_id]
    payload = finding.to_dict()
    payload["why"] = spec.description
    payload["remediation"] = spec.remediation
    return payload


def trace_report_payload(
    report: EvaluationReport,
    events: list[TraceEvent],
    policy: Policy,
    *,
    trace_sha256: str,
    trace_source: str | Path | None,
    policy_source: str | Path | None = None,
    run_id: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    session_id = events[0].session_id if events else None
    payload = base_provenance(
        agentack_version=__version__,
        kind="trace",
        session_id=session_id,
        run_id=run_id,
        evaluated_at=evaluated_at,
    )
    payload.update(
        {
            "input": trace_input_provenance(
                trace_sha256=trace_sha256,
                policy=policy,
                trace_source=trace_source,
                policy_source=policy_source,
            ),
            "adapter": None,
            "actions": [item.to_dict() for item in trace_action_identities(events)],
            "result": {
                "status": report.status,
                "event_count": report.events,
                "finding_count": len(report.findings),
                "rule_counts": report.rule_counts,
                "findings": [_finding_payload(item) for item in report.findings],
            },
        }
    )
    return payload


def adapter_report_payload(
    result: AdapterTestResult,
    *,
    run_id: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    payload = base_provenance(
        agentack_version=__version__,
        kind="adapter",
        session_id=result.session_id,
        run_id=run_id,
        evaluated_at=evaluated_at,
    )
    payload.update(
        {
            "input": adapter_input_provenance(result.evidence_sha256),
            "adapter": {
                "name": result.adapter,
                "display_name": result.display_name,
                "version": result.adapter_version,
            },
            "actions": [item.to_dict() for item in result.actions],
            "result": {
                "status": result.status,
                "checks": [check.to_dict() for check in result.checks],
                "notes": list(result.notes),
            },
        }
    )
    return payload


def write_json_report(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sarif_level(severity: str) -> str:
    return {"critical": "error", "high": "error", "medium": "warning", "low": "note"}[severity]


def _run_properties(document: dict[str, Any]) -> dict[str, Any]:
    run = document["run"]
    input_data = document["input"]
    trace = input_data.get("trace") or {}
    policy = input_data.get("policy") or {}
    evidence = input_data.get("evidence") or {}
    adapter = document.get("adapter") or {}
    return {
        "agentackReportSchemaVersion": document["report_schema_version"],
        "runId": run["run_id"],
        "evaluationKind": run["kind"],
        "evaluatedAt": run["evaluated_at"],
        "sessionId": run.get("session_id"),
        "traceSchemaVersion": trace.get("schema_version"),
        "traceSha256": trace.get("sha256"),
        "policySha256": policy.get("sha256"),
        "evidenceSha256": evidence.get("sha256"),
        "adapterName": adapter.get("name"),
        "adapterVersion": adapter.get("version"),
        "status": document["result"]["status"],
        "actionIdentities": document["actions"],
    }


def trace_sarif_payload(report: EvaluationReport, document: dict[str, Any]) -> dict[str, Any]:
    rules = []
    for rule_id, spec in RULES.items():
        rules.append(
            {
                "id": rule_id,
                "name": spec.title.replace(" ", ""),
                "shortDescription": {"text": spec.title},
                "fullDescription": {"text": spec.description},
                "help": {"text": spec.remediation},
                "defaultConfiguration": {"level": _sarif_level(spec.severity)},
                "properties": {"standards": list(spec.standards)},
            }
        )
    results = []
    source_name = (document["input"].get("trace") or {}).get("source")
    for finding in report.findings:
        spec = RULES[finding.rule_id]
        result: dict[str, Any] = {
            "ruleId": finding.rule_id,
            "level": _sarif_level(finding.severity),
            "message": {"text": finding.message},
            "properties": {
                "actionId": finding.action_id,
                "approvalId": finding.approval_id,
                "standards": list(finding.standards),
                "remediation": spec.remediation,
            },
        }
        if source_name and finding.line is not None:
            result["locations"] = [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": source_name},
                        "region": {"startLine": finding.line},
                    }
                }
            ]
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "automationDetails": {"id": document["run"]["run_id"]},
                "tool": {
                    "driver": {
                        "name": "AgentAck",
                        "version": __version__,
                        "informationUri": "https://github.com/sylvesterkaczmarek/agentack",
                        "rules": rules,
                    }
                },
                "properties": _run_properties(document),
                "results": results,
            }
        ],
    }


def _adapter_rule_id(label: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_")
    return f"ADAPTER_{slug}"


def adapter_sarif_payload(result: AdapterTestResult, document: dict[str, Any]) -> dict[str, Any]:
    rules = []
    results = []
    for check in result.checks:
        rule_id = _adapter_rule_id(check.label)
        rules.append(
            {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": check.label},
            }
        )
        if check.status not in {"FAIL", "INCOMPLETE"}:
            continue
        results.append(
            {
                "ruleId": rule_id,
                "level": "error" if check.status == "FAIL" else "warning",
                "message": {"text": check.detail},
                "properties": {"checkStatus": check.status},
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "automationDetails": {"id": document["run"]["run_id"]},
                "tool": {
                    "driver": {
                        "name": "AgentAck",
                        "version": __version__,
                        "informationUri": "https://github.com/sylvesterkaczmarek/agentack",
                        "rules": rules,
                    }
                },
                "properties": _run_properties(document),
                "results": results,
            }
        ],
    }


def write_sarif(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
