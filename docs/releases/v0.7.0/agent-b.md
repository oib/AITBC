# v0.7.0 Cross-Chain Bridge Basics — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add bridge config fields, missing RPC endpoints (unlock, balance, health, batch), fix CLI bridge commands, add bridge monitoring, and write integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/` and `/opt/aitbc/cli/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/rpc/bridge.py apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py apps/blockchain-node/src/aitbc_chain/network/bridge_manager.py apps/blockchain-node/src/aitbc_chain/config.py cli/aitbc_cli/commands/bridge.py aitbc/constants.py
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/test_bridge_suite.py apps/blockchain-node/tests/test_v070_bridge_basics.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add bridge config fields + bridge constants | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py`, `aitbc/constants.py` | ✅ |
| B2 | Add missing RPC endpoints: unlock, balance, health, status alias, batch | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py`, `apps/blockchain-node/src/aitbc_chain/rpc/router.py`, `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ✅ |
| B3 | Fix CLI bridge commands — replace broken stubs with BridgeClient calls | 🔴 P0 | `cli/aitbc_cli/commands/bridge.py` | ✅ |
| B4 | Add bridge monitoring — health checks, stuck transfer detection, metrics | High | `apps/blockchain-node/src/aitbc_chain/network/bridge_manager.py` | ✅ |
| B5 | Wire CLI node bridge commands to actual RPC | Medium | `cli/aitbc_cli/commands/node/bridge.py` | ✅ |
| B6 | Integration tests — unlock, balance, health, batch, monitoring, CLI | 🔴 P0 | `apps/blockchain-node/tests/test_v070_bridge_basics.py` (new) | ✅ |
| B7 | Verify mypy + ruff + pytest clean | High | — | ✅ |

---

## B1: Bridge Config + Constants

In `aitbc/constants.py`, add bridge constants:
```python
# Bridge defaults
BRIDGE_FEE_BASIS_POINTS = 10       # 0.1% bridge fee
BRIDGE_TIMEOUT_SECONDS = 300       # 5 minutes for cross-chain transfer
BRIDGE_RETRY_LIMIT = 3             # retry attempts for failed bridge ops
BRIDGE_BATCH_SIZE = 10             # max transfers per batch operation
BRIDGE_MONITOR_INTERVAL = 60       # seconds between health checks
BRIDGE_STUCK_TRANSFER_TIMEOUT = 3600  # 1 hour — transfers pending longer are flagged
```

In `apps/blockchain-node/src/aitbc_chain/config.py`, add to `Settings` class (near existing `bridge_release_enabled` at line 290):
```python
    # Bridge configuration (v0.7.0)
    bridge_timeout: int = 300
    bridge_retry_limit: int = 3
    bridge_fee_basis_points: int = 10
    bridge_supported_chains: str = ""  # comma-separated list of chain IDs
    bridge_batch_size: int = 10
    bridge_monitor_interval: int = 60
    bridge_stuck_transfer_timeout: int = 3600
```

---

## B2: Missing RPC Endpoints

In `cross_chain/bridge.py`, add a `refund_transfer()` method to `CrossChainBridge`:
```python
async def refund_transfer(self, transfer_id: str, sender: str) -> BridgeTransfer:
    """Refund a pending bridge transfer — return locked funds to sender.

    Only transfers in 'pending' or 'locked' status can be refunded.
    Completed/confirmed transfers cannot be refunded.
    """
    # Get transfer record, verify status is pending/locked
    # Return amount (minus fee) to sender balance
    # Create BRIDGE_REFUND transaction
    # Update transfer record to 'refunded'
```

Also add `get_bridge_balance()` method:
```python
async def get_bridge_balance(self, chain_id: str | None = None) -> dict[str, int]:
    """Get total locked amount per chain (sum of pending/locked transfers)."""
    # Query CrossChainTransfer where status in (pending, locked)
    # Group by source_chain, sum amount
```

Also add `batch_lock()` and `batch_confirm()` methods.

In `rpc/bridge.py`, add endpoints:
- `POST /bridge/unlock` — calls `refund_transfer()`, requires signature
- `GET /bridge/balance/{chain_id}` — calls `get_bridge_balance()`
- `GET /bridge/health` — returns bridge health status (active transfers, pending count, last error)
- `GET /bridge/status/{transfer_id}` — alias to existing `GET /bridge/transfer/{transfer_id}`
- `POST /bridge/batch/lock` — calls `batch_lock()`
- `POST /bridge/batch/confirm` — calls `batch_confirm()`

Register all new endpoints in `rpc/router.py` (following the existing pattern at lines 776-810).

---

## B3: Fix CLI Bridge Commands

In `cli/aitbc_cli/commands/bridge.py` (currently 78 lines, broken), replace the three broken commands (`start`, `status`, `stop` — which call non-existent endpoints) with:

- `aitbc bridge lock --target-chain --sender --recipient --amount [--asset] [--source-chain]` — calls `BridgeClient.lock()`
- `aitbc bridge confirm --transfer-id --confirmer --signature --proof-file` — calls `BridgeClient.confirm()`
- `aitbc bridge unlock --transfer-id --sender --signature` — calls `BridgeClient.unlock()`
- `aitbc bridge status --transfer-id` — calls `BridgeClient.get_transfer()`
- `aitbc bridge pending [--chain-id]` — calls `BridgeClient.list_pending()`
- `aitbc bridge balance --chain-id` — calls `BridgeClient.get_balance()`
- `aitbc bridge health` — calls `BridgeClient.health()`

Use `aitbc.bridge.BridgeClient` (from A1) instead of raw `AITBCHTTPClient`. The CLI commands should be async-compatible (use `asyncio.run()` wrapper if needed, following existing CLI patterns).

Remove the fallback-to-simulated-data pattern — if the RPC endpoint is unavailable, report the error clearly.

---

## B4: Bridge Monitoring

In `network/bridge_manager.py`, add:
1. `health_check()` method — ping active bridges, return health status per bridge
2. `detect_stuck_transfers()` method — query `CrossChainTransfer` for transfers pending longer than `bridge_stuck_transfer_timeout`, log warnings
3. `get_metrics()` method — return dict with: active_bridge_count, pending_transfer_count, stuck_transfer_count, total_locked_amount
4. `_monitor_loop()` background task — runs every `bridge_monitor_interval` seconds, calls `health_check()` + `detect_stuck_transfers()`, logs anomalies

The monitoring is additive — it does not change the existing bridge connection management logic.

---

## B5: CLI Node Bridge Commands

In `cli/aitbc_cli/commands/node/bridge.py` (currently 52 lines, stubs), replace simulated data with actual RPC calls:
- `aitbc node bridge request <target_island_id>` — calls `POST /islands/bridge`
- `aitbc node bridge approve <request_id> <approving_node_id>` — calls bridge manager approve
- `aitbc node bridge reject <request_id> [--reason]` — calls bridge manager reject
- `aitbc node bridge list-bridges` — calls `GET /bridge/health` or bridge manager list

---

## B6: Integration Tests

Create `apps/blockchain-node/tests/test_v070_bridge_basics.py`:
- `test_bridge_unlock_refund` — lock then unlock returns funds to sender
- `test_bridge_unlock_completed_rejected` — cannot unlock a completed transfer
- `test_bridge_balance` — balance reflects locked transfers
- `test_bridge_balance_empty_chain` — zero balance for chain with no transfers
- `test_bridge_health` — health endpoint returns status
- `test_bridge_status_alias` — /bridge/status/{id} returns same as /bridge/transfer/{id}
- `test_bridge_batch_lock` — batch lock creates multiple transfers
- `test_bridge_batch_confirm` — batch confirm processes multiple transfers
- `test_bridge_batch_lock_empty_rejected` — empty batch rejected
- `test_bridge_batch_lock_exceeds_limit_rejected` — batch over max size rejected
- `test_bridge_monitor_stuck_detection` — stuck transfer detected after timeout
- `test_bridge_monitor_metrics` — metrics endpoint returns correct counts
- `test_cli_bridge_lock` — CLI lock command calls correct endpoint
- `test_cli_bridge_status` — CLI status command calls correct endpoint
- `test_cli_bridge_health` — CLI health command calls correct endpoint

---

## B7: Verification

```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/ cli/aitbc_cli/commands/bridge.py cli/aitbc_cli/commands/node/bridge.py aitbc/constants.py
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/test_bridge_suite.py apps/blockchain-node/tests/test_v070_bridge_basics.py tests/unit/test_bridge_sdk.py -q -o addopts="" --timeout=30
```

---

## Coordination Protocol

No shared files are touched by both agents. Agent A creates new files in `aitbc/bridge/`. Agent B modifies files in `apps/blockchain-node/` and `cli/`. Agent B consumes Agent A's `BridgeClient` and types — Agent A must complete A1 before Agent B starts B3 (CLI uses BridgeClient).

### Sequencing

1. **Agent A goes first** — A1 (BridgeClient + types) and A2 (proof utils) can proceed immediately
2. **Agent B B1, B2, B4 can proceed in parallel** with Agent A — they don't depend on `aitbc/bridge/`
3. **Agent B B3 (CLI fix) depends on A1** — CLI uses `BridgeClient`
4. **Agent B B5 (node bridge CLI) can proceed in parallel** — uses existing `/islands/bridge` endpoint
5. **Agent B B6 (tests) depends on B2** — tests the new endpoints
6. **Agent B B7 (verify) runs last**

### Deferred to v0.7.1 / v0.7.2

The following are explicitly **NOT** in v0.7.0 scope:
- **v0.7.1**: Block header signing by proposers, multi-sig validation, time-locked transactions, cross-chain signature verification, bridge event auditing, external security audit
- **v0.7.2**: Merkle proof verification (`merkle_patricia_trie.verify_proof`), proposer-set membership checking, block header signature verification, finality tracking, validator set epoch transitions, `BRIDGE_RELEASE_ENABLED` fence removal

The `BRIDGE_RELEASE_ENABLED=false` fence **remains in place** throughout v0.7.0. The confirm/release path stays gated until v0.7.2 completes full cryptographic verification.

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.0 — Cross-Chain Bridge Basics
**Agent**: Agent B (Apps & Infrastructure)
