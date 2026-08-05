# v0.22 Open Tasks — Agent Split

This document records the remaining open findings from the v0.22 re-verification
pass and assigns them to Agent A or Agent B for continued work.

See [`release.log`](./release.log) for the full ledger, evidence, and verification
commands.

## Agent A — Core / Shared / Bridge / Infrastructure

Focus: `aitbc/`, `apps/blockchain-node`, `apps/blockchain-event-bridge`,
`apps/blockchain-explorer`, `contracts/`, ops/scripts, shared packages, and
infrastructure-wide findings.

- **CORE** — CORE-02/04/08/09/10/11/12/13/15/16/18/19/20/21/22/25/26/28/29

- **Contracts** — SC-05/06/08/09/10/11/12/14
- **Ops** — OPS-03/04/06/07/08/09/10/12/14/15/16/17/18
- **Packages** — PKG-01 through PKG-14
- **Tests/docs** — TEST-02 through TEST-08; DOC-02 through DOC-07

## Agent B — Apps / CLI / Service Layer

Focus: `apps/*` (except core blockchain/bridge/explorer), `cli/`, and
service-level auth/endpoint findings.

- **APP-54** — `simple_exchange` on stdlib `http.server` and fail-open API key
- **CLI** — CLI-02/03/05/06/07/08/09/10/13

## Notes

- APP-54 is the only remaining concrete application-level finding.
- All other APP findings tracked in `v0.22/release.log` are closed as of this
  re-verification pass.
- Cross-area items (e.g. CLI-13, TEST-08) may require both agents to coordinate.

## Quick Action Plans

These are bite-sized sequencing suggestions for the Agent A open areas. They are not
specifications; pattern discovery and architectural validation are still required before any
implementation.

### CORE

1. **Broken-on-first-use fixes** — CORE-01, CORE-05, CORE-06, CORE-12 (redis import,
   sync `QueuePool` in async engine, closed cursor return, self-contradictory CORS defaults).
   Each is a single-file, testable bug.
2. **Security defaults / fail-closed** — CORE-03 (default deny in `ROUTE_SECURITY_MATRIX`),
   CORE-23 (`ZKProof.verified` and `ReplicationProof.status` default to untrusted),
   CORE-28 (duplicate `BRIDGE_VALIDATOR_SET_GRACE_PERIOD`), CORE-29 (`hmac.compare_digest`
   in `htlc.verify_secret`).
3. **Auth / bridge / lifecycle** — CORE-04 (API key JSON store races + multi-worker),
   CORE-17 (multisig casing), CORE-18 (circuit-breaker lock), CORE-19 (subscription
   `stop()` cleanup), CORE-22 (`migration_timestamp` random hex), CORE-26 (hardcoded
   `http://localhost:PORT` endpoints).
4. **Money / floats in core** — CORE-07/21/27 (`SyncedOffer.price`, `price_oracle`,
   `integration_layer` trade submission).
5. **Rate limiters & request ID** — CORE-08/09/10/11 (limiter name collision, key eviction,
   consolidation, request-ID propagation), CORE-13 (size guard), CORE-14 (CSP
   `unsafe-eval`), CORE-15/16/20/24/25.

### Contracts

1. **Quick wins** — SC-09 (constructor zero-address validation), SC-14 (remove
   `contracts/GPURegistry.sol` stub or move out of compiled tree).
2. **No-op upgrades** — SC-08 (`TreasuryManager`, `DAOGovernanceEnhanced`,
   `PerformanceAggregator`, `StakingPoolFactory` `upgrade()` only increments version).
3. **Unbounded loops** — SC-05 (`distributeAgentEarnings`), SC-06
   (`_slashAllStakesForAgent`), SC-12 (`getBountyStats`). Likely the highest Solidity
   effort; consider pull-based reward accounting and batched slash operations.
4. **Deploy safety** — SC-10 (mainnet mock token confirmation gate), SC-11
   (`deploy-testnet.sh` argument parsing and dead `deploy.js` reference).

### Ops

1. **Scanner & gate fixes** — OPS-01 (secret-scanner excludes), OPS-14 (placeholder
   secret gate path), OPS-13 (READMEs for high-risk `scripts/` dirs).
2. **Secret rotation safety** — OPS-05/06/07 (CLI arg visibility, `sed` special-character
   escaping, backup retention).
3. **Script hardening** — OPS-04 (rollback confirmation), OPS-15 (quote `db_name` in
   psql), OPS-16 (replace `eval` with array invocation), OPS-18 (env/flag override for
   genesis node).
4. **Deployment cleanup** — OPS-10 (Node.js install checksum), OPS-11 (deduplicate and
   validate container deploy scripts), OPS-12 (remove `solve-github-prs.sh` main-push
   bypass).
5. **Destructive migration** — OPS-02/03/08 (`scale_balances_3600x.py`) need careful
   design; treat as release-blocker, not quick-fix.

### Packages

1. **Resource cleanup** — PKG-01/02/12 (AITBC HTTP client leaks and malformed-receipt
   crashes in SDK; `CoordinatorAPIClient.close()` / context manager).
2. **Shared ORM / auth** — PKG-04 (`aitbc_shared.orm` engine cache & context manager),
   PKG-11 (crypto verifier exception logging).
3. **Toolchain consistency** — PKG-05/06 (remove `@ts-nocheck`, add missing
   `devDependencies`), PKG-13 (Python >=3.13 and build backend consistency).
4. **SDK / web behaviour** — PKG-07 (agent SDK cli path and command splitting), PKG-08/09/14
   (wallet theme/preference hooks, SSR guard), PKG-03 (plugin loader sandbox — large).

### Tests / Docs

1. **Repo hygiene** — TEST-05 (delete obsolete `test_marketplace_api.py`), TEST-06
   (relocate shell test scripts to `tests/orchestrator.d/` or `tests/tooling/`), DOC-05
   (prune `docs/agent-outputs/`), DOC-06/07 (merge duplicate dirs, archive
   `pre-boilerplate-backup`).
2. **Quick doc fixes** — DOC-01 (README version badge), DOC-04 (merge/rename
   `quick-start.md` vs `quickstart.md`).
3. **Test gaps** — TEST-01 (wallet SQLModel metadata collision; fix and write at least one
   wallet unit test), TEST-02 (regenerate or delete `TEST_STATUS_SUMMARY.md`), DOC-02
   (canonical OpenAPI location).
4. **Larger test reorganization** — TEST-03 (unskip property tests), TEST-04 (mock or
   containerize production suites), TEST-07/08 (orchestrator shell, staking/archive
   cleanup).
