# AITBC scripts

Product, deployment, testing and maintenance scripts for the AITBC
monorepo. Nothing here runs against a live `/var` or `/etc` path from a
test or pin run — every destructive-capable script takes a scratch-dir
override. Fleet-only operations tooling lives in the separate private
`aitbc-ops` repository and is intentionally absent here.

## Entry points

- `deployment/setup.sh` — node deployment entry point
  (`BLOCKCHAIN_MODE=hub|follower`, `--open-island`, role/profile env).
- `deployment/update.sh` — update a deployed node to a new checkout.
- `ops/` — product-side operator helpers that must remain in the public
  checkout (genesis/snapshot verification, peer-key management, bootstrap
  env rendering). Fleet reset, failover, bridge and website helpers are in
  `aitbc-ops`.
- `maintenance/` — per-node backup, audit and genesis-reset helpers used by
  product commands and units.
- `ci/` — CI gates and generated-artifact checks
  (`check-version-consistency.py` is the canonical copy, wired into
  `make version-check`; `export-requirements.sh` regenerates the pinned
  requirements files from `poetry.lock`).

## Areas

- `security/` — `scan_secrets.py`, `dependency-scan.sh` and friends.
- `monitoring/` — the product health check (`health_check.sh`); fleet
  Prometheus/alerting machinery is in `aitbc-ops`.
- `testing/` — sandboxed product regression pins.
- `docs/` — `gen_master_index.py` regenerates `docs/MASTER_INDEX.md`.
- `setup/`, `services/`, `agent/` — per-service install and workflow helpers.
- `dev/`, `development/` — dev-node tooling.
- `utils/` — misc utilities.
- `release/`, `templates/`, `config/`, `notifications/`, `zk/`,
  `aitbc-cli/`, `aitbc-miner/`, `lint/`, `maintenance/`, `performance/`,
  `quality/`, `gpu/` — area tooling; read the directory before assuming a
  script is wired anywhere.

## Conventions

- Shell scripts run with `set -euo pipefail` (enforced by pre-commit).
- Python scripts target the repo venv (`venv/bin/python`) or system
  `python3`; no bare `python`.
- A script that is not wired from `Makefile`, `setup.sh`, `update.sh`,
  docs or a systemd unit is probably dead or demo — check its caller
  list before trusting it.
