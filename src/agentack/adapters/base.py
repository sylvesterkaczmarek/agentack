from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

CheckStatus = Literal["PASS", "FAIL", "INCOMPLETE", "SKIP"]
TestStatus = Literal["PASS", "FAIL", "INCOMPLETE"]


@dataclass(frozen=True)
class AdapterStatus:
    name: str
    display_name: str
    installed: bool
    testable: bool
    executable: str | None = None
    version: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class CheckResult:
    label: str
    status: CheckStatus
    detail: str


@dataclass(frozen=True)
class AdapterTestResult:
    adapter: str
    display_name: str
    status: TestStatus
    checks: tuple[CheckResult, ...]
    notes: tuple[str, ...] = ()


class AgentAdapter(ABC):
    """Interface for agent-specific discovery and approval-integrity tests."""

    name: str
    display_name: str

    @abstractmethod
    def detect(self) -> AdapterStatus:
        raise NotImplementedError

    @abstractmethod
    def run_test(self) -> AdapterTestResult:
        raise NotImplementedError
