"""Portable CLI smoke checks. Synthetic descriptions are never executed."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile


def run(arguments: list[str], expected: int = 0) -> None:
    result = subprocess.run([sys.executable, "-m", "agentack", *arguments], capture_output=True, text=True, timeout=30)
    if result.returncode != expected:
        raise RuntimeError(f"{arguments[0]} returned {result.returncode}, expected {expected}: {result.stderr}")
    print(result.stdout.strip())


if __name__ == "__main__":
    run(["demo"])
    run(["coverage"])
    run(["demo", "secure"])
    run(["demo", "action-swap"], 1)
    with tempfile.TemporaryDirectory(prefix="agentack-smoke-") as directory:
        trace = Path(directory) / "secure.jsonl"
        run(["demo", "secure", "--write", str(trace)])
        incomplete = Path(directory) / "incomplete.jsonl"
        incomplete.write_bytes(b"\n".join(trace.read_bytes().splitlines()[:-1]) + b"\n")
        run(["check", str(incomplete)], 3)
    print("Offline CLI smoke checks passed.")
