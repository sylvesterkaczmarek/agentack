"""Evaluate the named synthetic corpus against the installed AgentAck package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from integrity_cases import cases, materialize  # noqa: E402
from agentack.adapters.claude_analysis import analyze_capture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    results = []
    for name, mutation, expected in cases():
        records, decisions = materialize(mutation)
        actual = analyze_capture(records, decisions).status
        results.append({"case": name, "expected": expected, "actual": actual, "correct": actual == expected})
    report = {
        "corpus": "approval-integrity-v1",
        "evidence_type": "SYNTHETIC_SOFTWARE_REGRESSION_ONLY",
        "case_count": len(results),
        "correct": sum(item["correct"] for item in results),
        "false_passes": sum(item["actual"] == "PASS" and item["expected"] != "PASS" for item in results),
        "false_failures": sum(item["actual"] == "FAIL" and item["expected"] == "PASS" for item in results),
        "results": results,
    }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0 if report["correct"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
