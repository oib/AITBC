# AITBC scripts

Operator, deployment, testing and maintenance scripts for the AITBC
monorepo. Nothing here runs against a live `/var` or `/etc` path from a
test or pin run — every destructive-capable script takes a scratch-dir
override.

## Entry points

- `deployment/setup.sh` — node deployment entry point
  (`BLOCKCHAIN_MODE=hub|follower`, `--open-island`, role/profile env).
- `deployment/update.sh` — update a deployed node to a new checkout.
- `ops/` — operator runbooks and helpers (bridge-admin.sh, reset/backup
  tooling, contract monitoring, fleet checks).
- `ci/` — CI gates and generated-artifact checks
  (`check-version-consistency.py` is the canonical copy, wired into
  `make version-check`; `export-requirements.sh` regenerates the pinned
  requirements files from `poetry.lock`).

## Areas

- `security/` — `scan_secrets.py`, `dependency-scan.sh` and friends.
- `monitoring/` — health checks, alert configs, chain-isolation rules.
- `stress/` — the scenario-play stress harness (`run.sh`, `lib.sh`,
  `plays/`, `maturity-watcher.sh`).
- `testing/` — soak/load test drivers (`soak_test_consensus.py`,
  `test_workflow.sh`).
- `docs/` — `gen_master_index.py` regenerates `docs/MASTER_INDEX.md`.
- `migration/` — one-off data/schema migration helpers.
- `reset-harness/` — rehearsal/rollback harness for chain resets.
- `setup/`, `service-management/`, `services/`, `agent/`,
  `workflow-agent/` — per-service install and workflow helpers.
- `dev/`, `development/` — dev-node tooling.
- `utils/` — misc utilities.
- `release/`, `templates/`, `config/`, `notifications/`, `zk/`,
  `aitbc-cli/`, `aitbc-miner/`, `audit/`, `lint/`, `maintenance/`,
  `performance/`, `quality/`, `sync/`, `gpu/` — area tooling; read the
  directory before assuming a script is wired anywhere.

## Conventions

- Shell scripts run with `set -euo pipefail` (enforced by pre-commit).
- Python scripts target the repo venv (`venv/bin/python`) or system
  `python3`; no bare `python`.
- A script that is not wired from `Makefile`, `setup.sh`, `update.sh`,
  docs or a systemd unit is probably dead or demo — check its caller
  list before trusting it.
