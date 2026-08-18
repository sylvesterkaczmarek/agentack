from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .findings import RULES
from .models import EvaluationReport


def render_text(report: EvaluationReport) -> str:
    lines = [f"AgentAck  {report.status}"]
    if report.source:
        lines.append(f"Trace: {report.source}")
    lines.append(f"Events: {report.events}")
    lines.append(f"Findings: {len(report.findings)}")
    if not report.findings:
        lines.append("")
        lines.append("No approval-integrity violations detected by the enabled rules.")
        return "\n".join(lines)
    lines.append("")
    for finding in report.findings:
        location = f" line {finding.line}" if finding.line is not None else ""
        lines.append(f"{finding.severity.upper():8} {finding.rule_id} {finding.title}{location}")
        lines.append(f"         {finding.message}")
    return "\n".join(lines)


def write_json_report(path: str | Path, report: EvaluationReport) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sarif_level(severity: str) -> str:
    return {"critical": "error", "high": "error", "medium": "warning", "low": "note"}[severity]


def sarif_payload(report: EvaluationReport) -> dict[str, Any]:
    rules = []
    for rule_id, spec in RULES.items():
        rules.append(
            {
                "id": rule_id,
                "name": spec.title.replace(" ", ""),
                "shortDescription": {"text": spec.title},
                "fullDescription": {"text": spec.description},
                "defaultConfiguration": {"level": _sarif_level(spec.severity)},
                "properties": {"standards": list(spec.standards)},
            }
        )
    results = []
    for finding in report.findings:
        result: dict[str, Any] = {
            "ruleId": finding.rule_id,
            "level": _sarif_level(finding.severity),
            "message": {"text": finding.message},
        }
        if report.source and finding.line is not None:
            result["locations"] = [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": report.source},
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
                "tool": {
                    "driver": {
                        "name": "AgentAck",
                        "informationUri": "https://github.com/sylvesterkaczmarek/agentack",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }


def write_sarif(path: str | Path, report: EvaluationReport) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(sarif_payload(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
