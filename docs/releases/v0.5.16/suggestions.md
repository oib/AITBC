## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.5.16 Suggestions

## Status
**ALL 7 CONFIRMED BUGS STILL PRESENT** — Verified in codebase. All 7 bugs from the original investigation are still unfixed. 4 additional cross-service bugs added (Bugs 15-18) from suggestions.md investigation.

## Blockers
- Bridge `_validate_proof` in `cross_chain/bridge.py` is trivially forgeable. Any attacker with public transfer data can call `/bridge/confirm` to mint coins. Treat as P0 security issue until this ships.
- `fetch_blocks_range` and `bulk_import_from` in `sync.py` do not send `chain_id` to remote hubs. Multi-chain sync will silently import wrong chain blocks.
- `TransactionRequest` in `rpc/transactions.py` lacks `chain_id` field. Pydantic drops it silently, causing tx misrouting.

## Confirmed Live Bugs (verified in /opt/aitbc — ALL STILL PRESENT)
- `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` lines 21-31: `TransactionRequest` has no `chain_id` field. Line 90: `submit_transaction` calls `get_chain_id(None)`.
- `apps/blockchain-node/src/aitbc_chain/sync.py` line 280: `fetch_blocks_range` sends no `chain_id` param. Line 315: `bulk_import_from` sends no `chain_id` param.
- `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` lines 244-257: `_validate_proof` only checks field presence and value match — no signature, no block anchor, no Merkle proof.

## Additional Confirmed Issues (ALL STILL PRESENT — added as Bugs 15-18)
- `apps/agent-coordinator/src/app/websocket/agent_stream.py` line 361: hardcoded default `BLOCKCHAIN_RPC_URL=http://localhost:8202`. Actual port is `8006`. Also in `aitbc/crypto/transaction_service.py` line 21.
- `apps/agent-coordinator/src/app/websocket/agent_stream.py` line 364: `_submit_transaction` posts without `chain_id`.
- `apps/marketplace/src/marketplace_service/services/marketplace_service.py` lines 209-211: hardcoded DB path `/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db`.
- `apps/marketplace/src/marketplace_service/services/marketplace_service.py` lines 214-226: raw SQL queries directly against blockchain SQLite database.

## Recommendations
- Ship this before any other release. It unblocks v0.6.3, v0.6.5, v0.6.6, v0.6.7, v0.7.0, and v0.7.3.
- Fix `TransactionRequest` first: add `chain_id: str | None = None`, then thread it through `submit_transaction` and tx dict normalization.
- Fix `sync.py` `fetch_blocks_range` (add `chain_id=self._chain_id` to params) and `bulk_import_from` (add `chain_id=self._chain_id` to head request).
- Fix `_validate_proof`: add `block_height`, `block_hash`, `proposer_signature` to required fields; verify signature against known proposer pubkeys; verify block anchor via `rpc/block` lookup. (Full cryptographic verification deferred to v0.7.2.)
- Fix agent-coordinator: change default port from `8202` to `8006`, pass `chain_id` from transaction dict into the JSON payload.
- Fix marketplace: replace direct SQLite queries with blockchain RPC calls. Remove hardcoded path.
- Add regression tests for all 18 bugs that run in CI before merge.
- Consider making the bridge proof breaking change a separate commit with a clear security advisory.
