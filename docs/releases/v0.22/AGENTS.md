# v0.22 Open Tasks — Agent Split

This document assigns the remaining open v0.22 findings to Agent A or Agent B.

See [`release.log`](./release.log) for the full ledger, evidence, and verification
commands.

> **Agent B's list was verified against the code on 2026-08-05 (AITBC-91).** Four of its
> nine CLI items were already closed, and its single APP item was half-closed and
> mis-described. Corrected below, with what each claim was checked against. Agent A's list
> has **not** been re-verified — treat it with the same suspicion until it has been.

## Agent A — Core / Shared / Bridge / Infrastructure

Focus: `aitbc/`, `apps/blockchain-node`, `apps/blockchain-event-bridge`,
`apps/blockchain-explorer`, `contracts/`, ops/scripts, shared packages, and
infrastructure-wide findings.

- **CORE** — none remaining
- **Contracts** — SC-05/06/08/09/10/11/12/14
- **Ops** — OPS-03/04/06/07/08/09/10/12/14/15/16/17/18
- **Packages** — PKG-01 through PKG-14
- **Tests/docs** — TEST-02 through TEST-08; DOC-02 through DOC-07

**Not verified.** These are carried over as previously recorded. Given the Agent B hit
rate, expect some to be closed already.

## Agent B — Apps / CLI / Service Layer

Focus: `apps/*` (except core blockchain/bridge/explorer), `cli/`, and service-level
auth/endpoint findings.

### Open

- **APP-54** — `simple_exchange` runs on stdlib `http.server` (`server.py`, `db.py`)
  rather than the `src/<pkg>/` FastAPI layout every sibling service uses. This is why it
  cannot use shared `aitbc.auth` middleware and hand-rolls its own request handling. The
  largest remaining Agent B item; it is a service migration, not a patch.

### Closed under AITBC-91

| ID | Finding | Fix |
|---|---|---|
| CLI-03 | Credentials in a module-level dict — gone next invocation, while reporting "stored" | OS keyring when available, else a 0600 file store; the active backend is reported rather than silently chosen |
| CLI-05 | Multisig challenges process-local; `created_at` was `secrets.token_hex(8)` | Persisted to a 0600 store with a real ISO timestamp and a 1-hour TTL; verified working across separate processes |
| CLI-06 | Audit dir/files created with the process umask | Directory 0700, files created 0600 via `os.open` |
| CLI-10 | `secrets.json` written then chmod'ed — readable window | Created 0600 via `os.open`; parent dir 0700 |
| CLI-13 | `client.py` an unregistered 9-line stub with 0 commands | Removed, along with the four tests that existed only to assert it was empty |

### Already closed before this pass — do not re-do

| ID | Finding | Evidence |
|---|---|---|
| CLI-02 | `get_wallet_balance_in_chain` returned a placeholder `0.0` | Makes a real HTTP call to `/v1/chains/{id}/wallets/{id}/balance` |
| CLI-07 | Weak secret redaction in `env_validator` | `_looks_like_secret(key, value)` gates a `***REDACTED***` replacement |
| CLI-08 | `aitbc list` alias dropped parent context | Uses `ctx.invoke(wallet, ...)`; comment records that global flags are preserved |
| CLI-09 | `chain_manager` reported fabricated migration statistics | Hardcoded `10000`/`1000`/`300` replaced with `0` |
| APP-50 | exchange `_require_api_key` failed open when `EXCHANGE_API_KEY` was unset | Now sends 401; docstring: "A missing EXCHANGE_API_KEY is treated as an auth failure" |

The previous revision folded APP-50 into the APP-54 line as "`simple_exchange` on stdlib
`http.server` **and fail-open API key**". They are separate findings in opposite states,
and the combined wording would have sent someone to re-fix a closed one.

## Notes

- The previous claim that "APP-54 is the only remaining concrete application-level
  finding" and that "all other APP findings are closed" was not accurate. It contradicted
  `release.log`'s own Open table in the same directory, which listed APP-32, APP-33,
  APP-35 and APP-64. On checking those: **APP-32 and APP-64 are genuinely fixed** (the
  event bridge now has a persisted checkpoint and a reorg-tolerance buffer — the hardest
  of the four; the ledger simply was not updated). **APP-33 and APP-35 could not be
  confirmed closed** and should be treated as open.
- Cross-area items (e.g. TEST-08) may require both agents to coordinate.

## Convention

A finding is closed when its failure mode has been reproduced as a test, or the absence of
the defect demonstrated by executing the affected path — not when a plausible-looking
change has been made nearby. Both directions of error have already occurred in this
release: real findings recorded as fabricated after reading already-fixed code, and unfixed
findings recorded as closed without running anything.

## Quick Action Plans

Bite-sized sequencing for the Agent A areas. Not specifications; pattern discovery and
architectural validation still apply. **Verify each item is still open before starting.**

### Contracts

1. **Quick wins** — SC-09 (constructor zero-address validation), SC-14 (remove
   `contracts/GPURegistry.sol` stub or move out of the compiled tree).
2. **No-op upgrades** — SC-08 (`TreasuryManager`, `DAOGovernanceEnhanced`,
   `PerformanceAggregator`, `StakingPoolFactory` `upgrade()` only increments version).
3. **Unbounded loops** — SC-05 (`distributeAgentEarnings`), SC-06
   (`_slashAllStakesForAgent`), SC-12 (`getBountyStats`). Highest Solidity effort;
   consider pull-based reward accounting and batched slash operations.
4. **Deploy safety** — SC-10 (mainnet mock token confirmation gate), SC-11
   (`deploy-testnet.sh` argument parsing and dead `deploy.js` reference).

### Ops

1. **Scanner & gate fixes** — OPS-14 (placeholder secret gate path), OPS-13 (READMEs for
   high-risk `scripts/` dirs).
2. **Secret rotation safety** — OPS-06/07 (`sed` special-character escaping, backup
   retention). OPS-05 (argv visibility) is already closed.
3. **Script hardening** — OPS-04 (rollback confirmation), OPS-15 (quote `db_name` in
   psql), OPS-16 (replace `eval` with array invocation), OPS-18 (env/flag override for
   genesis node).
4. **Deployment cleanup** — OPS-10 (Node.js install checksum), OPS-11 (deduplicate and
   validate container deploy scripts), OPS-12 (remove `solve-github-prs.sh` main-push
   bypass).
5. **Destructive migration** — OPS-03/08 (`scale_balances_3600x.py`) need careful design;
   treat as release-blocker, not quick-fix.

### Packages

1. **Resource cleanup** — PKG-01/02/12 (HTTP client leaks and malformed-receipt crashes in
   the SDK; `CoordinatorAPIClient.close()` / context manager).
2. **Shared ORM / auth** — PKG-04 (`aitbc_shared.orm` engine cache & context manager),
   PKG-11 (crypto verifier exception logging).
3. **Toolchain consistency** — PKG-05/06 (remove `@ts-nocheck`, add missing
   `devDependencies`), PKG-13 (Python >=3.13 and build backend consistency).
4. **SDK / web behaviour** — PKG-07 (agent SDK cli path and command splitting),
   PKG-08/09/14 (wallet theme/preference hooks, SSR guard), PKG-03 (plugin loader sandbox
   — large).

### Tests / Docs

1. **Repo hygiene** — TEST-05 (delete obsolete `test_marketplace_api.py`), TEST-06
   (relocate shell test scripts), DOC-05 (prune `docs/agent-outputs/`), DOC-06/07 (merge
   duplicate dirs, archive `pre-boilerplate-backup`).
2. **Quick doc fixes** — DOC-04 (merge/rename `quick-start.md` vs `quickstart.md`).
   DOC-01 (README badge) is already closed.
3. **Test gaps** — TEST-02 (regenerate or delete `TEST_STATUS_SUMMARY.md`), DOC-02
   (canonical OpenAPI location). TEST-01 (wallet tests) is already closed.
4. **Larger test reorganization** — TEST-03 (unskip property tests), TEST-04 (mock or
   containerize production suites), TEST-07/08 (orchestrator shell, staking/archive
   cleanup).

## Adjacent finding, not yet ticketed

`cli/aitbc_cli/utils/__init__.py::encrypt_value` is base64, not encryption. `config.py
set-secret` describes itself as "Set an encrypted configuration value" and reports
"Secret saved (encrypted)". Anything relying on that wording is relying on obfuscation.
Noticed while fixing CLI-10; out of scope there, and it needs its own ticket.
