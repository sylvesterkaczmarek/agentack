"""Write four reproducible synthetic demonstrations and machine-readable reports."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

from agentack.demo import demo_events
from agentack.parser import write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error("output must be absent or an empty directory")
    args.output.mkdir(parents=True, exist_ok=True)
    secure = demo_events("secure")
    denied = [replace(event, decision="deny") if event.type == "approval_decision" else event for event in secure]
    scenarios = [
        ("valid-approval", secure, 0),
        ("changed-action", demo_events("action-swap"), 1),
        ("denied-but-executed", denied, 1),
        ("missing-evidence", secure[:-1], 3),
    ]
    manifest = {"evidence_type": "SYNTHETIC_SOFTWARE_DEMONSTRATION_ONLY", "scenarios": []}
    for name, events, expected in scenarios:
        trace = args.output / f"{name}.jsonl"
        report = args.output / f"{name}.json"
        sarif = args.output / f"{name}.sarif"
        write_jsonl(trace, events)
        result = subprocess.run(
            [sys.executable, "-m", "agentack", "check", str(trace), "--json", str(report), "--sarif", str(sarif)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != expected:
            raise RuntimeError(f"Unexpected outcome for {name}: {result.stdout} {result.stderr}")
        payload = json.loads(report.read_text(encoding="utf-8"))
        print(f"{name:<24} {payload['result']['status']}")
        manifest["scenarios"].append(
            {"name": name, "status": payload["result"]["status"], "expected_exit_code": expected}
        )
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
