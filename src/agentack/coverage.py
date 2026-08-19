from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CoverageState = Literal["TESTED", "GUARDED", "TRACE", "SKIP"]


@dataclass(frozen=True)
class CoverageRow:
    rule_id: str
    title: str
    trace: CoverageState
    claude: CoverageState
    codex: CoverageState
    note: str


LIVE_COVERAGE: tuple[CoverageRow, ...] = (
    CoverageRow("ACK001", "Required approval", "TESTED", "TESTED", "TRACE", "Claude exercises the live approval boundary; Codex remains deterministic-trace coverage only."),
    CoverageRow("ACK002", "Denied action", "TESTED", "TESTED", "TRACE", "Claude exercises live denial enforcement; Codex remains deterministic-trace coverage only."),
    CoverageRow("ACK003", "Exact action binding", "TESTED", "TESTED", "TRACE", "Claude compares live structured action identity; Codex remains deterministic-trace coverage only."),
    CoverageRow("ACK004", "Approval replay", "TESTED", "TESTED", "TRACE", "Claude exercises one-time approval replay; Codex remains deterministic-trace coverage only."),
    CoverageRow("ACK005", "Approval expiry", "TESTED", "TRACE", "TRACE", "Neither agent exposes a stable portable live approval-expiry clock for this suite."),
    CoverageRow("ACK006", "Lifecycle ordering", "TESTED", "GUARDED", "TRACE", "Claude validates live lifecycle evidence; retained Codex protocol analysis is research/regression, not a live claim."),
    CoverageRow("ACK007", "Denial route-around", "TESTED", "TESTED", "TRACE", "Claude exercises an alternate denied-intent route; Codex remains deterministic-trace coverage only."),
    CoverageRow("ACK008", "Interrupt bypass", "TESTED", "SKIP", "TRACE", "Claude Stop is not a user-interrupt signal; Codex has no verified deterministic standalone live boundary."),
    CoverageRow("ACK009", "Evidence completeness", "TESTED", "GUARDED", "TRACE", "Claude fails closed on missing live evidence; Codex remains deterministic-trace coverage only."),
)


def render_coverage() -> str:
    lines = [
        "AgentAck live coverage",
        "",
        f"{'Rule':<8} {'Trace':<9} {'Claude':<9} {'Codex':<9} Check",
    ]
    for row in LIVE_COVERAGE:
        lines.append(f"{row.rule_id:<8} {row.trace:<9} {row.claude:<9} {row.codex:<9} {row.title}")
    lines.extend(
        [
            "",
            "TESTED  deliberately exercised by the listed path",
            "GUARDED fail-closed evidence validation, without an induced live attack",
            "TRACE   deterministic trace coverage only for that live adapter",
            "SKIP    no reliable safe live boundary is claimed",
        ]
    )
    return "\n".join(lines)
