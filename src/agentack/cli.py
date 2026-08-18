from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .adapters.claude import ClaudeCodeAdapter, record_hook_event
from .demo import SCENARIOS, demo_events
from .engine import evaluate_events
from .findings import RULES
from .models import TraceValidationError
from .parser import read_jsonl_with_digest, write_jsonl
from .policy import Policy
from .provenance import trace_digest_from_events
from .report import (
    adapter_report_payload,
    adapter_sarif_payload,
    render_text,
    trace_report_payload,
    trace_sarif_payload,
    write_json_report,
    write_sarif,
)
from .ux import render_adapter_test, render_doctor

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INPUT_ERROR = 2
EXIT_INCOMPLETE = 3


def _policy(path: str | None) -> Policy:
    return Policy.from_toml(path) if path else Policy()


def _status_code(status: str) -> int:
    return {
        "PASS": EXIT_PASS,
        "FAIL": EXIT_FAIL,
        "INCOMPLETE": EXIT_INCOMPLETE,
    }[status]


def _output_error(exc: OSError) -> int:
    print(f"agentack: output error: {exc}", file=sys.stderr)
    return EXIT_INPUT_ERROR


def _write_machine_outputs(
    args: argparse.Namespace,
    *,
    json_payload: dict[str, Any],
    sarif_payload: dict[str, Any],
) -> int | None:
    json_output = getattr(args, "json_output", None)
    sarif_output = getattr(args, "sarif", None)
    if json_output and sarif_output:
        try:
            same_output = Path(json_output).resolve() == Path(sarif_output).resolve()
        except OSError as exc:
            return _output_error(exc)
        if same_output:
            print("agentack: output error: --json and --sarif must use different paths", file=sys.stderr)
            return EXIT_INPUT_ERROR
    try:
        if json_output:
            write_json_report(json_output, json_payload)
        if sarif_output:
            write_sarif(sarif_output, sarif_payload)
    except OSError as exc:
        return _output_error(exc)
    return None


def cmd_check(args: argparse.Namespace) -> int:
    try:
        policy = _policy(args.policy)
        events, trace_sha256 = read_jsonl_with_digest(args.trace)
    except (OSError, ValueError, TraceValidationError) as exc:
        print(f"agentack: input error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    report = evaluate_events(events, policy=policy, source=str(Path(args.trace)))
    document = trace_report_payload(
        report,
        events,
        policy,
        trace_sha256=trace_sha256,
        trace_source=args.trace,
        policy_source=args.policy,
    )
    output_status = _write_machine_outputs(
        args,
        json_payload=document,
        sarif_payload=trace_sarif_payload(report, document),
    )
    if output_status is not None:
        return output_status
    print(render_text(report))
    return _status_code(report.status)


def _demo_showcase() -> int:
    secure = evaluate_events(demo_events("secure"), source="demo:secure")
    broken = evaluate_events(demo_events("action-swap"), source="demo:action-swap")
    detected = "ACK003" in broken.rule_counts
    print("AgentAck demo")
    print()
    print(f"{'Secure approval flow':<30} {secure.status}")
    print(f"{'Action changed after approval':<30} {'DETECTED (ACK003)' if detected else 'MISSED'}")
    print()
    print("AgentAck binds the action shown for approval to the action that later executes.")
    print("The broken demo changes the command after approval; AgentAck detects the mismatch.")
    print()
    print("Next: agentack doctor")
    return EXIT_PASS if secure.status == "PASS" and detected else EXIT_FAIL


def cmd_demo(args: argparse.Namespace) -> int:
    if args.list:
        for scenario in SCENARIOS:
            print(scenario)
        return EXIT_PASS
    if args.scenario is None and not any((args.write, args.policy, args.json_output, args.sarif)):
        return _demo_showcase()

    scenario = args.scenario or "secure"
    try:
        events = demo_events(scenario)
        policy = _policy(args.policy)
        if args.write:
            write_jsonl(args.write, events)
    except (OSError, ValueError, TraceValidationError) as exc:
        print(f"agentack: input/output error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    report = evaluate_events(events, policy=policy, source=f"demo:{scenario}")
    trace_sha256 = trace_digest_from_events(events)
    document = trace_report_payload(
        report,
        events,
        policy,
        trace_sha256=trace_sha256,
        trace_source=args.write or f"demo-{scenario}.jsonl",
        policy_source=args.policy,
    )
    output_status = _write_machine_outputs(
        args,
        json_payload=document,
        sarif_payload=trace_sarif_payload(report, document),
    )
    if output_status is not None:
        return output_status
    print(render_text(report))
    return _status_code(report.status)


def _discovered_without_adapters() -> list[tuple[str, str, str | None]]:
    tools = (
        ("Codex CLI", "codex"),
        ("Gemini CLI", "gemini"),
        ("Cursor CLI", "cursor"),
    )
    discovered: list[tuple[str, str, str | None]] = []
    for display_name, binary in tools:
        path = shutil.which(binary)
        if path:
            discovered.append(
                (
                    display_name,
                    "DETECTED",
                    f"Found at {path}. AgentAck does not expose a live `{binary}` adapter yet.",
                )
            )
    return discovered


def cmd_doctor(args: argparse.Namespace) -> int:
    del args
    claude = ClaudeCodeAdapter().detect()
    print(render_doctor([claude], _discovered_without_adapters()))
    return EXIT_PASS


def cmd_test(args: argparse.Namespace) -> int:
    if args.agent != "claude":
        print(f"agentack: unsupported live adapter {args.agent!r}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    try:
        result = ClaudeCodeAdapter().run_test()
    except (OSError, ValueError) as exc:
        print(f"agentack: adapter error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    document = adapter_report_payload(result)
    output_status = _write_machine_outputs(
        args,
        json_payload=document,
        sarif_payload=adapter_sarif_payload(result, document),
    )
    if output_status is not None:
        return output_status
    print()
    print(render_adapter_test(result))
    return _status_code(result.status)


def cmd_hook(args: argparse.Namespace) -> int:
    # Claude Code reserves hook exit code 2 for a blocking decision.
    # Recorder failures must therefore use 1 so AgentAck never changes permission behavior.
    if args.agent != "claude":
        return 1
    try:
        raw = sys.stdin.buffer.read(1_000_001)
        record_hook_event(args.event, args.capture, raw)
    except (OSError, ValueError) as exc:
        print(f"agentack hook error: {exc}", file=sys.stderr)
        return 1
    return EXIT_PASS


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path)
    if target.exists() and not args.force:
        print(f"agentack: {target} already exists; use --force to replace it", file=sys.stderr)
        return EXIT_INPUT_ERROR
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(Policy().to_toml(), encoding="utf-8")
    except OSError as exc:
        return _output_error(exc)
    print(f"Wrote {target}")
    return EXIT_PASS


def cmd_rules(args: argparse.Namespace) -> int:
    if args.json:
        payload = {
            rule_id: {
                "severity": spec.severity,
                "title": spec.title,
                "description": spec.description,
                "standards": list(spec.standards),
                "remediation": spec.remediation,
            }
            for rule_id, spec in RULES.items()
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return EXIT_PASS
    for rule_id, spec in RULES.items():
        print(f"{rule_id}  {spec.severity.upper():8}  {spec.title}")
    return EXIT_PASS


def cmd_explain(args: argparse.Namespace) -> int:
    rule_id = args.rule_id.upper()
    spec = RULES.get(rule_id)
    if spec is None:
        print(f"agentack: unknown rule {rule_id}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    print(f"{spec.rule_id}  {spec.title}")
    print(f"Severity: {spec.severity}")
    print(f"Why: {spec.description}")
    print(f"Next: {spec.remediation}")
    if spec.standards:
        print("Relevant mappings: " + ", ".join(spec.standards))
    return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentack",
        description="Test whether human approval controls remain bound to the actions that execute.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="see a secure and a deliberately broken approval flow")
    demo.add_argument("scenario", nargs="?", choices=SCENARIOS)
    demo.add_argument("--list", action="store_true")
    demo.add_argument("--write", help="write one synthetic scenario to JSONL")
    demo.add_argument("--policy")
    demo.add_argument("--json", dest="json_output")
    demo.add_argument("--sarif")
    demo.set_defaults(func=cmd_demo)

    doctor = subparsers.add_parser("doctor", help="detect coding-agent integrations available on this machine")
    doctor.set_defaults(func=cmd_doctor)

    live_test = subparsers.add_parser("test", help="run a live approval-integrity test against a supported agent")
    live_test.add_argument("agent", choices=("claude",))
    live_test.add_argument("--json", dest="json_output")
    live_test.add_argument("--sarif")
    live_test.set_defaults(func=cmd_test)

    check = subparsers.add_parser("check", help="evaluate an existing AgentAck JSONL trace")
    check.add_argument("trace")
    check.add_argument("--policy")
    check.add_argument("--json", dest="json_output")
    check.add_argument("--sarif")
    check.set_defaults(func=cmd_check)

    init = subparsers.add_parser("init", help="write a starter policy")
    init.add_argument("path", nargs="?", default="agentack.toml")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    rules = subparsers.add_parser("rules", help="list security rules")
    rules.add_argument("--json", action="store_true")
    rules.set_defaults(func=cmd_rules)

    explain = subparsers.add_parser("explain", help="explain one rule and its next action")
    explain.add_argument("rule_id")
    explain.set_defaults(func=cmd_explain)

    return parser


def _private_hook_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentack _hook", add_help=False)
    parser.add_argument("agent", choices=("claude",))
    parser.add_argument(
        "--event",
        required=True,
        choices=("PreToolUse", "PermissionRequest", "PostToolUse", "PostToolUseFailure", "SessionEnd"),
    )
    parser.add_argument("--capture", required=True)
    parser.set_defaults(func=cmd_hook)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "_hook":
        args = _private_hook_parser().parse_args(raw[1:])
        return int(args.func(args))
    parser = build_parser()
    args = parser.parse_args(raw)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
