"""Verify an already-built wheel from a fresh environment outside the checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import venv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
    with tempfile.TemporaryDirectory(prefix="agentack-wheel-") as directory:
        workspace = Path(directory)
        environment = workspace / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

        def run(arguments: list[str]) -> None:
            subprocess.run([str(python), *arguments], cwd=workspace, env=env, check=True, timeout=300)

        run(["-m", "pip", "install", "--disable-pip-version-check", "--no-index", "--no-deps", str(wheel)])
        run(
            [
                "-c",
                "import agentack, pathlib, sys; p=pathlib.Path(agentack.__file__).resolve(); assert pathlib.Path(sys.prefix).resolve() in p.parents; print('Installed wheel:', agentack.__version__, p)",
            ]
        )
        run(["-m", "unittest", "discover", "-s", str(root / "tests"), "-v"])
        run([str(root / "scripts/verify_corpus.py")])
        run([str(root / "scripts/smoke.py")])
    print(
        json.dumps(
            {"wheel": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "verification": "PASS"},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
