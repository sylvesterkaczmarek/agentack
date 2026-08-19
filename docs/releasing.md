# Releasing AgentAck

AgentAck uses PyPI Trusted Publishing through GitHub Actions. No long-lived PyPI API token is required.

## Trusted Publisher

For the PyPI project `agentack`, configure the GitHub Actions publisher with:

- owner: `sylvesterkaczmarek`
- repository: `agentack`
- workflow: `release.yml`
- environment: `pypi`

For the first release, a pending publisher can create the PyPI project automatically.

## Release process

The package version is the single source of truth in `pyproject.toml` and must match `agentack.__version__` and `CITATION.cff`.

To release version `X.Y.Z`, create the branch:

```text
release/vX.Y.Z
```

from the exact commit already present on `main`.

`.github/workflows/release.yml` then:

1. verifies the release branch matches the package version and the commit is contained in `main`;
2. refuses to continue if the corresponding `vX.Y.Z` tag already exists;
3. builds wheel and sdist and runs metadata validation;
4. publishes those artifacts to PyPI using OIDC Trusted Publishing;
5. creates a clean virtual environment and installs that exact version from the public PyPI index;
6. verifies the installed `agentack` CLI reports the expected version and runs `demo` and `coverage`;
7. creates the `vX.Y.Z` GitHub tag/release from the same commit and attaches the same distributions.

The release branch is only a trigger and can be deleted after a successful release.

A failed PyPI publish or failed public-install verification does not create the GitHub release.
