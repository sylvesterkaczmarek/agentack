from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .demo import SCENARIOS, demo_events
from .engine import evaluate_events
from .findings import RULES
from .models import TraceValidationError
from .parser import read_jsonl, write_jsonl
from .policy import Policy
from .report import render_text, write_json_report, write_sarif


def _policy(path: str | None) -> Policy:
    return Policy.from_toml(path) if path else Policy()


def _emit_outputs(args: argparse.Namespace, report) -> None:  # type: ignore[no-untyped-def]
    print(render_text(report))
    if getattr(args, "json_output", None):
        write_json_report(args.json_output, report)
    if getattr(args, "sarif", None):
        write_sarif(args.sarif, report)


def cmd_check(args: argparse.Namespace) -> int:
    try:
        policy = _policy(args.policy)
        events = read_jsonl(args.trace)
    except (OSError, ValueError, TraceValidationError) as exc:
        print(f"agentack: input error: {exc}", file=sys.stderr)
        return 2
    report = evaluate_events(events, policy=policy, source=str(Path(args.trace)))
    _emit_outputs(args, report)
    return 0 if report.status == "PASS" else 1


def cmd_demo(args: argparse.Namespace) -> int:
    if args.list:
        for scenario in SCENARIOS:
            print(scenario)
        return 0
    try:
        events = demo_events(args.scenario)
        policy = _policy(args.policy)
    except (ValueError, OSError) as exc:
        print(f"agentack: {exc}", file=sys.stderr)
        return 2
    if args.write:
        write_jsonl(args.write, events)
    report = evaluate_events(events, policy=policy, source=f"demo:{args.scenario}")
    _emit_outputs(args, report)
    return 0 if report.status == "PASS" else 1


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path)
    if target.exists() and not args.force:
        print(f"agentack: {target} already exists; use --force to replace it", file=sys.stderr)
        return 2
    target.write_text(Policy().to_toml(), encoding="utf-8")
    print(f"Wrote {target}")
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    if args.json:
        payload = {
            rule_id: {
                "severity": spec.severity,
                "title": spec.title,
                "description": spec.description,
                "standards": list(spec.standards),
            }
            for rule_id, spec in RULES.items()
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    for rule_id, spec in RULES.items():
        print(f"{rule_id}  {spec.severity.upper():8}  {spec.title}")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    rule_id = args.rule_id.upper()
    spec = RULES.get(rule_id)
    if spec is None:
        print(f"agentack: unknown rule {rule_id}", file=sys.stderr)
        return 2
    print(f"{spec.rule_id}  {spec.title}")
    print(f"Severity: {spec.severity}")
    print(spec.description)
    if spec.standards:
        print("Relevant mappings: " + ", ".join(spec.standards))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentack",
        description="Test whether human approval controls remain bound to the actions that execute.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="evaluate a JSONL trace")
    check.add_argument("trace")
    check.add_argument("--policy")
    check.add_argument("--json", dest="json_output")
    check.add_argument("--sarif")
    check.set_defaults(func=cmd_check)

    demo = subparsers.add_parser("demo", help="run a deterministic synthetic scenario")
    demo.add_argument("scenario", nargs="?", default="secure", choices=SCENARIOS)
    demo.add_argument("--list", action="store_true")
    demo.add_argument("--write", help="write the synthetic trace to JSONL")
    demo.add_argument("--policy")
    demo.add_argument("--json", dest="json_output")
    demo.add_argument("--sarif")
    demo.set_defaults(func=cmd_demo)

    init = subparsers.add_parser("init", help="write a starter policy")
    init.add_argument("path", nargs="?", default="agentack.toml")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    rules = subparsers.add_parser("rules", help="list security rules")
    rules.add_argument("--json", action="store_true")
    rules.set_defaults(func=cmd_rules)

    explain = subparsers.add_parser("explain", help="explain one rule")
    explain.add_argument("rule_id")
    explain.set_defaults(func=cmd_explain)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
