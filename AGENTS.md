# AITBC — guide for agents working in this repo

AITBC is a Python 3.13 monorepo of FastAPI microservices, a CLI, shared
libraries, and Solidity contracts for running a multi-island blockchain
network where GPU providers sell compute and clients submit AI jobs that
are paid, executed, and settled on-chain.

This file is the contributor/agent guide. User-facing documentation lives in
`docs/`; the high-level product overview is `README.md`. Deployment-specific
operator details (concrete hosts, validator keys, internal remotes)
intentionally do not live in this repository.

## Repository layout

- `apps/` — services (`blockchain-node`, `coordinator-api`, `market`,
  `trading`, `exchange`, `pool-hub`, `agent-coordinator`, ...), each with
  `src/` + `tests/`
- `cli/aitbc_cli/` — the `aitbc` command-line tool
- `mcp-server/` — MCP server exposing node operations to agents
- `contracts/` — Solidity contracts (Foundry + Hardhat suites)
- `packages/py/` — shared Python packages
- `scripts/` — deployment, ops, ci, monitoring helpers
- `website/` — white-label public hub site (rendered via
  `scripts/ops/render-website.sh` + `/etc/aitbc/website.env`)
- `docs/` — user, deployment, and testing docs; release logs under
  `docs/releases/`
- `tests/` — repo-level pytest suites

## Deploy a node

`scripts/deployment/setup.sh` is the entry point:

- Own island: `BLOCKCHAIN_MODE=hub`
- Join an existing island: `setup.sh --open-island <hub-url> --node-id <id>`
- Roles: `MARKET_ROLE=shop|customer`, `HARDWARE_PROFILE=gpu`

See `docs/getting-started/setup-service-selection.md` for the role/service
matrix and `docs/agent/guides/open-island-joining-guide.md` for the join
flow.

Deployment conventions worth knowing:

- Services are systemd units reading env files from `/etc/aitbc/*.env`.
  **`EnvironmentFile=` does not strip inline `#` comments** — a comment on
  an assignment line becomes part of the value. Annotate env files on their
  own line.
- No bare `python` on deployed nodes: use `venv/bin/python` inside the
  checkout (or `python3` for the system interpreter). Poetry lives in its
  own venv.
- The chain database path is `DATA_DIR/data/<chain_id>/chain.db`
  (`apps/blockchain-node/src/aitbc_chain/config.py`); `DATA_DIR` comes from
  `AITBC_DATA_DIR`/`--data-dir`. `sqlite3 <path>` silently *creates* an
  empty DB on a wrong path — verify the path before probing.
- `coordinator-api` runs `alembic upgrade head` at service start
  (`ExecStartPre`); a failed migration fails the start deliberately. If the
  service won't start after an update, check `journalctl -u
  aitbc-coordinator-api` for alembic output first.

## Development workflow

- Conventional commits: `type(scope): description`.
- Pre-commit hooks gate commits — do not use `--no-verify`; the same checks
  run in CI (`.github/workflows/ci.yml`).
- Python checks: `ruff`, `mypy` (baseline `scripts/ci/mypy-baseline.txt`),
  `pytest` suites under `tests/` and `apps/*/tests/`.
- Release notes go in `docs/releases/v<major>.<minor>/v<version>_change.log`
  via `scripts/release/append-changelog.sh <file>` (entry on stdin; refuses
  duplicate `### ` headers and avoids heredoc-over-ssh quoting damage).

## No secrets in the repo

- Never commit tokens, private keys, wallet secrets, or API credentials.
- Tools that need a token read it from the environment or a file outside the
  repo (e.g. `GITEA_TOKEN` from env or `~/.gitea_token`).
- Never write credentials into git remote URLs or `~/.git-credentials`; use
  a credential helper or interactive entry.
- If a secret is accidentally committed: rotate it immediately, scrub it
  from history (`git filter-repo`), and force-push.

## Shell script conventions

- Preserve the existing shebang; only change it with a concrete reason.
- POSIX-portable scripts use `#!/bin/sh` (Debian's `dash`) and must not gain
  Bash-only syntax. Bash-only features require `#!/bin/bash`.
- Never change a host's `/bin/sh` or a user's login shell to make script
  work easier.

## Smart contract test suites (two of them)

`contracts/` carries **two** independent suites; both must pass and neither
covers what the other does.

- **Foundry**: `cd contracts && forge test` (and `contracts/governance`).
  Coverage needs `forge coverage --ir-minimum` — `via_ir` is required by the
  project and plain `forge coverage` disables it. If solc reports
  stack-too-deep without a location, the usual cause is a `public` mapping
  over a struct with many fields: keep such mappings `internal` and expose
  `getX() returns (Struct memory)`.
- **Hardhat (mocha)**: `cd contracts && npx hardhat test` — needs a Node
  toolchain and `node_modules`. This suite is the *only* coverage for
  `AgentStaking`, `PaymentProcessor`, and `EscrowService`.

## Wallet key mismatches

If a wallet's stored key does not match the address it is supposed to
control, do **not** regenerate the key from the address — a public address
cannot be reversed. A regenerated key is a new wallet unrelated to the
original funds. Recover from the original seed phrase/backup if it exists;
otherwise deprecate the wallet and migrate to a fresh, safely-backed-up one.
This is a data-integrity issue, not a code bug.

## MCP server for agent tooling

`mcp-server/aitbc_mcp_server.py` (typed tools in
`mcp-server/aitbc_mcp_rpc_tools.py`) exposes live node operations: nodes,
services, chain state, accounts, transactions, blocks, mempool, bridge,
GPU, AI jobs, market, escrow, disputes, governance. Read-only tools are the
default; mutating tools are `dry_run=true`-gated and require
`confirm=true`. Prefer typed MCP tools over raw SSH when operating a node.

## Task and history tracking

`AGENTS.md` carries conventions only. Release history lives in
`docs/releases/` change logs; component status is in
`docs/releases/STATUS.md`.
