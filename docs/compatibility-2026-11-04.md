# Compatibility assessment on 4 November 2026

## Executed checks

| Component | Observation | Limit |
| --- | --- | --- |
| AgentAck candidate | Local deterministic suite, named corpus and full-runtime type checking | Software verification only |
| Python | 3.14.7 on macOS | Other versions/platforms are delegated to the existing CI matrix |
| Claude Code | Executable not installed on the review machine | No live run or current-binary compatibility result |
| Codex CLI | 0.148.0; version/help commands and local JSON-schema export succeeded | No model turn, approval prompt or real execution boundary was exercised |
| Codex schema | Structured command approval, isolated-thread options and turn interruption were present | Schema presence does not establish live approval integrity |

No model calls, permission decisions, account changes or package publications were made during this assessment.

## Claude contract changes

The implementation now checks a recognizable version and advertised CLI flags before offering a supervised test. It requires an interactive terminal, restricts tool selection to Bash, supplies a temporary settings file and an explicit empty MCP configuration, and retains the native human permission prompts. These controls do not establish an operating-system sandbox; managed settings and the installed CLI remain outside AgentAck's control.

Capture correlates decisions with `session.id`, `tool_use_id` and `tool_name`. Missing correlation stays incomplete. PermissionRequest has no tool invocation ID in the documented hook contract, so its association is restricted to one unambiguous sequential probe window. Overlap or duplicate presentation cannot establish a pass.

## Sources checked

Official documentation accessed on 4 November 2026:

- Claude hooks: https://code.claude.com/docs/en/hooks
- Claude telemetry: https://code.claude.com/docs/en/monitoring-usage
- Claude CLI flags: https://code.claude.com/docs/en/cli-reference
- Codex App Server: https://developers.openai.com/codex/app-server/

These are protocol references, not executed compatibility evidence. Codex documents request, client decision, request resolution and completion as distinct events. AgentAck retains its detection/trace-only status until those boundaries are demonstrated in an actual supervised run.

## Supervised validation still required

Run `agentack test claude --json result.json --sarif result.sarif` from an interactive terminal on the intended machine. Retain the exact AgentAck commit/version, agent version, operating system, test date, settings, per-probe outcomes and any missing evidence. Follow the native approval/denial instructions; do not automate the human's choices.

A failed preflight, missing session correlation, unknown telemetry source, incomplete outcome or interrupted session must not be reported as a successful live validation. A live result applies only to the recorded synthetic paths and exact tested version.
