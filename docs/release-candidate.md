# Reviewing the 0.7 candidate

This is an unpublished release candidate. Merge, final version selection and publication require a separate review decision.

## Offline verification

From an isolated checkout and virtual environment:

```bash
python -m pip install -e '.[dev]'
make check
make release-check
python scripts/verify_wheel.py dist/agentack-0.7.0rc1-py3-none-any.whl
python scripts/verify_corpus.py --json corpus-result.json
python scripts/showcase.py --output ./agentack-showcase
```

The wheel check installs into a fresh environment with dependencies disabled and runs outside the source checkout. It confirms the imported package location, runs the complete test suite and evaluates the named corpus against the installed package.

The corpus is `approval-integrity-v1`. All its records are synthetic. Its counts measure classification of named software fixtures, not attack prevalence or production-agent effectiveness. The additional generated checks enumerate all 120 permutations of the five-event secure lifecycle and pair 100 seeded action substitutions with 100 valid controls.

## Independent review focus

Check the seven original Claude false-pass reproductions, direct-API mixed sessions and empty inputs, malformed CLI fields, exact interpreter/context identity, conflicting decision handling, persistent approval, missing capture, clock assumptions and backward compatibility. Review the distinction between missing evidence and affirmative violations.

Re-run the suite against the exact PR head, inspect the public API/report changes and verify package contents. Do not infer that the source checkout and a public PyPI installation contain the same version.

## Publication gate

The release workflow reuses the complete CI workflow for the exact candidate commit. Building and publication depend on that result. It also checks that the release commit is contained in main, the branch matches the package version and the tag does not already exist. Prerelease version strings are rejected.

After independent approval, select a final version, update package and citation metadata and prepare the final release branch. This candidate does not create that branch, a release tag, a GitHub release or a PyPI upload.

Current live compatibility limitations are recorded in [the dated assessment](compatibility-2026-11-04.md).
