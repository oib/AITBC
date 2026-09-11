# Dependency tiers: which hosts get which requirements file

## The two tiers

| tier | file | contents | who gets it |
|---|---|---|---|
| **test** | `requirements-test.txt` | pytest + asyncio/cov/mock/rerunfailures/timeout, coverage, fakeredis | **every** host |
| **dev** | `requirements-dev.txt` | the above **plus** mypy, ruff, pre-commit, bandit, safety, pip-audit, ipython, `types-*` | hosts marked as dev nodes |

The test tier is not optional anywhere. `pyproject.toml`'s
`[tool.pytest.ini_options] addopts` unconditionally passes `--reruns`, which
only `pytest-rerunfailures` provides, so a host without it cannot *collect* the
suite at all — every invocation dies with `unrecognized arguments`. A node that
cannot run its own tests cannot be verified after a deploy.

Test-tier versions are not pinned in `requirements-test.txt`. They come from
`requirements-dev.txt` used as a pip constraints file, and that file is
generated from `poetry.lock` by `scripts/ci/export-requirements.sh` — so the
two tiers cannot drift apart. `tests/test_requirements_tiers.py` enforces both
the subset relationship and the addopts/plugin correspondence.

## How a host is marked

Being a dev node is configuration, not hostname or hardware, and it is
independent of a node's blockchain role — a host can be a dev node *and* an
ordinary follower, so the axes compose. Any one of these marks a host:

```bash
touch /etc/aitbc/dev-node                  # marker file
AITBC_DEV_NODE=1                           # in /etc/aitbc/blockchain.env, or the environment
```

`scripts/deployment/install-profiles.sh` installs the test tier unconditionally
and the dev tier only when the marker is present. To change a host's tier, add
or remove the marker and re-run the installer.

Which hosts carry which tier is deployment-specific and deliberately not
recorded here.

## History

The profile installer exports with `poetry export --only main`, so for a long
time the primary deployment path installed **no** test runner at all. That is
the script's design, not drift — but it collided with the mandatory `--reruns`
addopt, leaving every host provisioned that way unable to run pytest in any
form. The hosts that were complete were complete only by accident: they had
been provisioned through `deployment/setup.sh`'s fallback branch, which
installed `requirements-dev.txt` wholesale (and did it with `|| warning`, so a
failure there would have been silent too). The tier split exists so that
neither the gap nor the silent-failure path can recur.
