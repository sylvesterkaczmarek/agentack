# Verifying AgentAck 0.7.0

From an isolated checkout and virtual environment:

```bash
python -m pip install -e '.[dev]'
make release-check
python scripts/verify_wheel.py dist/agentack-0.7.0-py3-none-any.whl
python scripts/verify_corpus.py --json corpus-result.json
python scripts/showcase.py --output ./agentack-showcase
```

The showcase directory must be new or empty. The wheel verifier installs without dependencies into a fresh environment, removes source-path overrides, verifies the import location and runs the full suite, named corpus and smoke checks outside the checkout.

The suite has 237 tests, including 32 additional tests from the independent-review repairs. Generated checks evaluate all 120 orderings of a five-event lifecycle and 100 seeded substitutions paired with 100 valid controls. The separately named corpus has 20 synthetic cases. These are software checks, not estimates of agent vulnerability rates or human behaviour.

## Integration status

The core checker and synthetic evidence analysis can be verified without an agent account. Claude live probes require a real interactive terminal and a person answering native prompts. Fresh supervised validation was not run during this release and the integration is explicitly experimental. Codex is detection/trace-only; no live validation is claimed.

## Release evidence

See [the 0.7.0 record](release-0.7.0.md). Confirm that GitHub CI corresponds to the exact commit being reviewed and that a public installation reports 0.7.0. Retain the original input/report when re-evaluating older traces under the [new identity and report semantics](migration-0.7.md).
