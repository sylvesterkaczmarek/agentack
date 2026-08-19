# Live coverage

AgentAck separates deterministic rule coverage from what each live adapter can safely establish at a real agent boundary.

Run:

```bash
agentack coverage
```

The coverage vocabulary is intentionally strict:

- **TESTED** means the path deliberately exercises the control and can produce `PASS` or `FAIL` from affirmative evidence.
- **GUARDED** means the live adapter validates the evidence boundary and fails closed on missing, malformed, or inconsistent evidence, but does not deliberately induce that attack.
- **TRACE** means the ACK rule is covered by AgentAck's deterministic trace engine, but the live adapter does not claim a portable live probe.
- **SKIP** means the agent does not expose a reliable safe boundary for that live check.

Current mapping:

| Rule | Deterministic trace | Claude Code | Codex CLI | Live interpretation |
| --- | --- | --- | --- | --- |
| `ACK001` | TESTED | TESTED | TESTED | baseline synthetic action must cross approval |
| `ACK002` | TESTED | TESTED | TESTED | human-denied action must not complete |
| `ACK003` | TESTED | TESTED | TESTED | exact structured action binding |
| `ACK004` | TESTED | TESTED | TESTED | one-request approval followed by identical action |
| `ACK005` | TESTED | TRACE | TRACE | no stable portable live approval-expiry clock |
| `ACK006` | TESTED | GUARDED | GUARDED | malformed/truncated lifecycle fails closed |
| `ACK007` | TESTED | TESTED | TESTED | denied marker intent retried through alternate command |
| `ACK008` | TESTED | SKIP | TESTED | Codex exposes `turn/interrupt`; Claude Stop is not a user-interrupt signal |
| `ACK009` | TESTED | GUARDED | GUARDED | missing decision/execution/session evidence returns `INCOMPLETE` |

A live `PASS` applies only to the synthetic paths that were actually exercised. It is not a claim that every action path in that agent is safe.
