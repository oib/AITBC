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
- Consensus rule for apply-time validation: a change to `state/`,
  `consensus/`, or `sync_*` transaction-application code either keeps
  behaviour identical for existing block versions — proved by replaying
  historical blocks (`apps/blockchain-node/tests/test_historical_replay.py`
  and `scripts/ops/replay-chain.py`) — or waits behind a new version
  height. Never tighten a check unconditionally for already-recorded eras.
- Release notes go in `docs/releases/v<major>.<minor>/v<version>_change.log`
  via `scripts/release/append-changelog.sh <file>` (entry on stdin; refuses
  duplicate `### ` headers and avoids heredoc-over-ssh quoting damage).
  Once a version's tag is cut its log is frozen — entries for post-tag
  commits go to the next version's log, creating `v<next>_change.log` if
  it does not exist yet; never append post-tag work to a tagged log.
- Release tags are cut at the deploy commit: a fleet-wide deploy of
  consensus/sync/apply changes gets the next `v<major>.<minor>.<patch>` tag,
  the version's changelog is finalised in the tagged commit (later entries
  go to the next version's log), and the release is published at the same
  time. Consensus-activation height pins get their own tag whose release
  notes state the activation height. Docs-only or single-service deploys
  may stay untagged. `scripts/monitoring/fleet-config-check.sh` reports
  each host's checkout commit against the latest tag.

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

## Bridge payout account — no manual sends

Never send an ad-hoc transaction from the bridge payout account
(`BRIDGE_PAYOUT_*`). Every payout must go through a ledger row:
SUBMITTED rows hold a signed envelope whose nonce may still land — a
manual send can occupy that nonce and strand the deposit forever, and
two sends from the same account is how double payments happen. Operator
actions use the monitor's own commands, never a raw RPC submit:

```bash
cd /opt/aitbc && venv/bin/python -m bridge_monitor.admin <command>
#   status <tx_hash>                inspect a ledger row
#   manual-payout <to> <amount>     manual payout, same ledger-first path
#   abandon-and-resign <tx_hash>    abandon a stuck SUBMITTED payout —
#                                   refuses unless the account nonce has
#                                   passed the envelope nonce AND the
#                                   envelope hash is not sealed
#   write-off <tx_hash> --reason …  terminal write-off (reason required)
```

Serialization: at most one payout envelope is in flight at a time, so a
SUBMITTED row that can neither seal nor abandon blocks every deposit
queued behind it (head-of-line blocking). The monitor alerts when the
oldest SUBMITTED row outlives its recovery horizon
(`BRIDGE_STUCK_PAYOUT_BLOCKS`, default `rebroadcast_blocks ×
max_rebroadcasts`) and when the PENDING_RETRY queue reaches
`BRIDGE_QUEUE_ALERT_DEPTH` (default 5). Release a blocked row
deliberately:

- **Envelope unsealed + account nonce passed** → `abandon-and-resign`
  re-queues the deposit for a fresh payout (also runs automatically in
  the sweep).
- **Payout sealed with a failed status**, or a genuinely lost row →
  `write-off` (with `--unpaid-with-recipient` when the row still carries
  a valid recipient), then `manual-payout` if the recipient is still
  owed — never re-sign the spent envelope.

Payout sizing is locked and bounded: the first computed `ait_amount` is
stored on the row and a retry pays exactly that amount (a recompute only
ever runs when no price was recorded — `amount_ait='0'` — and stores the
prices it used). A single payout may not exceed
`BRIDGE_MAX_PAYOUT_FRACTION` (default 0.5) of the payout wallet balance
and, when set, the absolute `BRIDGE_MAX_PAYOUT_AIT` ceiling — the stricter
of the two binds (the fraction shrinks as the float drains, so the fixed
bound stays predictable). An over-cap deposit lands FAILED and alerts — resolve it with a float
top-up plus `manual-payout` (deliberately uncapped) or a refund. The
low-float alert counts the balance *minus* payouts already committed on
non-terminal rows, not the raw balance.

`BRIDGE_FUNDING_SOURCES` is a comma-separated allowlist of Ethereum-side
sender addresses whose inflows are float top-ups, not deposits: they are
recorded as `FUNDING` ledger rows (deduplicated, never paid out). The match
is case-insensitive on both sides, so a canary deposit must come from a
clearly different sender — a case variant still matches. Without it a top-up
takes the deposit path and fails on the missing recipient.

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
