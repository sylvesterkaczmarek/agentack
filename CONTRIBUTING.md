# Contributing

Contributions that improve approval-integrity testing, evidence quality, adapters, portability, or documentation are welcome.

## Development setup

Python 3.11 or later is required.

```bash
git clone https://github.com/sylvesterkaczmarek/agentack.git
cd agentack
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
make check
```

On Windows, activate the virtual environment using the normal PowerShell or Command Prompt command and run the equivalent Python commands directly if `make` is unavailable.

## Changes

Keep the deterministic core framework-agnostic. Agent-specific behavior belongs under `src/agentack/adapters/`.

For a new live adapter:

1. document the exact official event or control boundary it observes;
2. distinguish observed facts from inference;
3. use `INCOMPLETE` when required evidence is unavailable;
4. avoid replacing or weakening the agent's native permission system;
5. use harmless synthetic probes;
6. add mocked integration tests that cover success, failure, and missing evidence;
7. update the supported-integration table only after the adapter genuinely works.

Do not add placeholder `agentack test` targets.

## Pull requests

Keep changes focused. Add regression tests for security-relevant fixes and update public documentation when behavior changes.

Before opening a pull request, run:

```bash
make check
```

For packaging changes, also run:

```bash
make release-check
```

## Security reports

Do not open a public issue for an exploitable security vulnerability. Follow [`SECURITY.md`](SECURITY.md).
