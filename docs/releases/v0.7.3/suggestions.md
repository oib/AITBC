## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.7.3 Suggestions

## Status
**RESCOPED** — v0.7.3 is now scoped to **same-chain governance only** (on-chain proposals, voting, execution). Cross-chain governance and parameter automation are deferred to v0.8.x. See AGENTS.md for the grounded A/B task split.

**VERIFIED 2026-06-29** — All claims in this file checked against codebase. Several stale claims corrected.

## Gaps
- ~~Changelog lacks reference files for governance and pool hub interactions.~~ → **CONFIRMED**: No reference files. AGENTS.md now includes specific file paths and line numbers.
- ~~Cross-chain governance relies on bridge maturity not yet verified (v0.7.0-v0.7.2).~~ → **CONFIRMED**: v0.7.0+v0.7.1 complete, v0.7.2 Agent A complete, Agent B in progress. Cross-chain governance deferred to v0.8.x.
- ~~No validation that `PoolHub` can actually expose parameters that governance is meant to change. Note: PoolHub app does not exist yet (confirmed in v0.6.7 investigation) — it will be created in v0.6.7.~~ → **STALE CLAIM CORRECTED**: Pool Hub EXISTS (v0.6.7 complete, commit `5bb3803bd`). It has `PoolHubBlockchainClient`, `Settings` (blockchain_rpc_url=8202, default_chain_id="ait-hub"), miner registration, reward distribution. However, Pool Hub does NOT expose a parameter change API — that's a v0.8.x prerequisite for parameter automation.

## Additional Verified Findings (2026-06-29)
- Governance service is 991 lines (src only, not ~2.5K as some analyses claimed — that count includes alembic, examples, etc.)
- Domain models complete: Proposal, Vote, Delegation, GovernanceToken, TokenStake, DaoTreasury, ProposalExecutionLog, TransparencyReport (8 SQLModel tables)
- 20+ API endpoints exist in `main.py` (410 lines)
- `execute_proposal()` at `main.py:167-188` is LOCAL ONLY — sets `tx_hash: None`, no blockchain tx
- No Settings/BaseSettings in governance service — no blockchain_rpc_url, no chain_id config
- TransactionRequest at `rpc/transactions.py:21-32` has `type: str = "TRANSFER"` — arbitrary string, no enum
- Tx processing at `poa.py:348-366` reads `tx.content.get("type", "TRANSFER")` — already handles arbitrary types
- Blockchain-node has `GET /rpc/account/{address}` for balance queries (verified at `rpc/accounts.py:30`)
- Change.log migration guide references stale port 8006 — correct port is 8202

## Recommendations
- ~~Verify current PoolHub parameter surface after v0.6.7 ships, before designing governance proposals.~~ → Pool Hub exists but has no parameter API. Parameter automation deferred to v0.8.x.
- ~~Start with same-chain governance; add bridge-based cross-chain voting only after v0.7.2 is operational.~~ → **ADOPTED**: v0.7.3 is same-chain only. Cross-chain deferred to v0.8.x.
- ~~Require an internal review pass (architecture + security) before coding starts.~~ → Internal review via comprehensive test coverage (same as v0.7.1, v0.7.2).
- ~~v0.7.2 is now rescoped to in-process verification (no external oracle). Cross-chain governance proposals must use the in-process verification path.~~ → Still valid for v0.8.x cross-chain governance.
- **NEW**: Fix stale port 8006→8202 in change.log migration guide.
- **NEW**: Create `aitbc/governance/` shared package (Agent A) before wiring governance service (Agent B).
