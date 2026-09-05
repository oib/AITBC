# Fleet roles: which hosts carry which dependency tier

## The two tiers

| tier | file | contents | who gets it |
|---|---|---|---|
| **test** | `requirements-test.txt` | pytest + asyncio/cov/mock/rerunfailures/timeout, coverage, fakeredis | **every** host |
| **dev** | `requirements-dev.txt` | the above **plus** mypy, ruff, pre-commit, bandit, safety, pip-audit, ipython, `types-*` | IDE host + designated dev nodes only |

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

## Roster

| host | role | GPU | dev tier | why |
|---|---|---|---|---|
| `at1` (IDE) | authoring, the only push point | — | **yes** | where code is written, linted, committed and mirrored |
| `node0` | validator, GPU | yes | no | validator with recovery + backup timers; keep the runtime lean |
| `node1` | follower, GPU | yes | no | production follower |
| `node2` | follower, GPU, service workhorse | yes | **yes** | runs the widest set of services (coordinator-api, marketplace, miner, pool-hub, edge, whisper, ffmpeg, hermes-agent), so it is the most representative place to reproduce and test integration behaviour |
| `hub.aitbc` | public hub, api-gateway | no | no | public-facing, and the smallest box by disk (~11 GB free, 3 GB RAM) — it must stay minimal |
| `hub2.aitbc` | follower | no | **yes** | spare capacity on disk (~425 GB) and the lightest service load (8 units), so tooling work there disturbs nothing |

`hub2` has only ~1 GB of RAM. It is fine for pytest and ruff; memory-hungry
tools (notably a full `mypy` run over the tree) may struggle there. Prefer
`node2` or the IDE host for those.

## How a host is marked

Being a dev node is configuration, not hostname or hardware — `node2` is a dev
node *and* an ordinary GPU follower, so the axes compose. Any one of these
marks a host:

```bash
touch /etc/aitbc/dev-node                  # marker file (what the fleet uses)
AITBC_DEV_NODE=1                           # in /etc/aitbc/blockchain.env, or the environment
```

`scripts/deployment/install-profiles.sh` installs the test tier unconditionally
and the dev tier only when the marker is present. To change a host's role,
add or remove the marker and re-run the installer.

## History

The profile installer exports with `poetry export --only main`, so for a long
time the primary deployment path installed **no** test runner at all. That is
the script's design, not drift — but it collided with the mandatory `--reruns`
addopt, leaving `node0`, `node2` and `hub2` unable to run pytest in any form.
`node1` and `hub.aitbc` were complete only because they happened to be
provisioned through `deployment/setup.sh`'s fallback branch, which installed
`requirements-dev.txt` wholesale (and did it with `|| warning`, so a failure
there would have been silent too). The tier split exists so that neither the
gap nor the silent-failure path can recur.
