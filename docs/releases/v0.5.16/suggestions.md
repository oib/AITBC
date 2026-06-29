## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.5.16 Suggestions

## Status
**ALL 7 ORIGINAL BUGS FIXED** — Re-verified against current codebase (2026-06-29). The earlier "ALL 7 CONFIRMED BUGS STILL PRESENT" claim was stale; all 7 were fixed across v0.5.16–v0.6.7. 1 of the 7 (bridge proof validation) is partially fixed and fenced behind `BRIDGE_RELEASE_ENABLED=false` pending full cryptographic verification in v0.7.2. The "Additional Confirmed Issues" port claim was based on a backwards port direction (8202 is correct; 8006 is the stale port).

## Blockers
- ~~Bridge `_validate_proof` in `cross_chain/bridge.py` is trivially forgeable.~~ **PARTIALLY FIXED (v0.5.16)**: now requires `block_height`, `block_hash`, `proposer_signature`, `chain_id`. Proposer-set membership check + Merkle proof deferred to v0.7.2. Release path fenced behind `BRIDGE_RELEASE_ENABLED=false` (default) to prevent unauthorized minting until v0.7.2 ships.
- ~~`fetch_blocks_range` and `bulk_import_from` in `sync.py` do not send `chain_id` to remote hubs.~~ **FIXED (v0.5.16)**: `fetch_blocks_range` sends `chain_id=self._chain_id` (sync.py:311); `bulk_import_from` head request sends `chain_id=self._chain_id` (sync.py:347).
- ~~`TransactionRequest` in `rpc/transactions.py` lacks `chain_id` field.~~ **FIXED (v0.5.16)**: `chain_id: str | None = None` field present (transactions.py:24); `submit_transaction` calls `get_chain_id(tx_data.chain_id)` (transactions.py:91).

## Confirmed Live Bugs (re-verified in /opt/aitbc on 2026-06-29 — ALL FIXED)
- ~~`apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` lines 21-31: `TransactionRequest` has no `chain_id` field.~~ **FIXED**: line 24 has `chain_id: str | None = None`; line 91 passes `tx_data.chain_id` to `get_chain_id`.
- ~~`apps/blockchain-node/src/aitbc_chain/sync.py` line 280: `fetch_blocks_range` sends no `chain_id` param.~~ **FIXED**: line 311 sends `chain_id=self._chain_id`. `bulk_import_from` head request (line 347) also sends `chain_id=self._chain_id`. 63 `chain_id` references throughout sync.py.
- ~~`apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` lines 244-257: `_validate_proof` only checks field presence and value match.~~ **PARTIALLY FIXED**: now requires `block_height`, `block_hash`, `proposer_signature`, `chain_id` (lines 263-269+). Proposer-set membership check deferred to v0.7.2; release fenced behind `BRIDGE_RELEASE_ENABLED=false`.

## Additional Confirmed Issues (re-verified on 2026-06-29 — ALL FIXED or NOT A BUG)
- ~~`apps/agent-coordinator/src/app/websocket/agent_stream.py` line 361: hardcoded default `BLOCKCHAIN_RPC_URL=http://localhost:8202`. Actual port is `8006`.~~ **NOT A BUG**: 8202 is the CORRECT blockchain RPC port (blockchain-node `config.py:89`). 8006 is the stale port. The original suggestion had the port direction backwards. `aitbc/crypto/transaction_service.py:41` also correctly uses 8202.
- ~~`apps/agent-coordinator/src/app/websocket/agent_stream.py` line 364: `_submit_transaction` posts without `chain_id`.~~ **FIXED (v0.6.5)**: lines 365-366 add `chain_id` from `CHAIN_ID` env var if missing before posting.
- ~~`apps/marketplace/src/marketplace_service/services/marketplace_service.py` lines 209-211: hardcoded DB path `/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db`.~~ **FIXED**: no `chain.db` or `/var/lib/aitbc` path references in marketplace service code (only in systemd unit `ReadWritePaths`). Service uses SQLAlchemy ORM.
- ~~`apps/marketplace/src/marketplace_service/services/marketplace_service.py` lines 214-226: raw SQL queries directly against blockchain SQLite database.~~ **FIXED**: no `sqlite3.connect` or raw SELECT in the service file — uses SQLAlchemy ORM (`self.session.execute`, `result.scalars()`).

## Recommendations
- ~~Ship this before any other release.~~ **COMPLETE**: v0.5.16 shipped; all 7 bugs fixed across v0.5.16–v0.6.7.
- Remaining work is the v0.7.2 bridge proof hardening (proposer-set membership + Merkle proof verification via `merkle_patricia_trie.verify_proof`). Release path stays fenced behind `BRIDGE_RELEASE_ENABLED=false` until v0.7.2 ships.
- Add regression tests for all 18 bugs that run in CI before merge. (Largely done across v0.5.16–v0.6.7 test suites.)
- Consider making the bridge proof breaking change a separate commit with a clear security advisory. (Still applicable for v0.7.2.)
