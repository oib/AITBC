# v0.8.1 Cross-Chain Offer Synchronization — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add offer sync config, offer sync service, discovery endpoint, sync endpoints, CLI commands, and tests.

**Working directory**: `/opt/aitbc/apps/trading/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1-A3 complete. v0.8.0 Agent B complete.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/trading/src/trading_service/ cli/aitbc_cli/commands/trade.py
cd /opt/aitbc && PYTHONPATH=apps/trading/src:aitbc ./venv/bin/python -m pytest apps/trading/tests/test_v081_offer_sync.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Offer sync config — Settings extensions (sync_enabled, sync_interval, staleness_thresholds) | 🔴 P0 | `apps/trading/src/trading_service/config.py` (extend) | ✅ |
| B2 | Offer sync service — OfferSyncService with polling loop per chain, incremental sync, conflict resolution, staleness detection | 🔴 P0 | `apps/trading/src/trading_service/services/offer_sync_service.py` (new) | ✅ |
| B3 | Discovery endpoint — POST /v1/trading/offers/discover | 🔴 P0 | `apps/trading/src/trading_service/main.py` (extend) | ✅ |
| B4 | Sync endpoints — POST /v1/trading/offers/sync, GET /v1/trading/offers/sync-status | 🔴 P0 | `apps/trading/src/trading_service/main.py` (extend) | ✅ |
| B5 | CLI commands — trade discover, sync, sync-status | Medium | `cli/aitbc_cli/commands/trade.py` (extend) | ✅ |
| B6 | Tests — sync, discovery, staleness, conflict resolution | High | `apps/trading/tests/test_v081_offer_sync.py` (new) | ✅ |

---

## B1: Offer Sync Config

Extend `apps/trading/src/trading_service/config.py`:
```python
sync_enabled: bool = True
sync_interval_seconds: int = 60
staleness_threshold_seconds: int = 300
per_chain_sync_intervals: dict[str, int] = {}  # chain_id -> interval
per_chain_staleness_thresholds: dict[str, int] = {}  # chain_id -> threshold
```

---

## B2: Offer Sync Service

Create `apps/trading/src/trading_service/services/offer_sync_service.py`:
- `OfferSyncService` — polling loop per chain
- Per-chain sync intervals from config
- Incremental sync (since last_sync)
- Conflict resolution (source-wins)
- Staleness detection + refresh
- Use Agent A's `OfferCache` from A3
- Use existing `BlockchainRPCClient` to query offers per chain

---

## B3: Discovery Endpoint

Add to `apps/trading/src/trading_service/main.py`:
- `POST /v1/trading/offers/discover` — discover offers across chains
- Query Agent A's `OfferCache` from A3
- Trigger on-demand sync if stale
- Return ranked, deduplicated results

---

## B4: Sync Endpoints

Add to `apps/trading/src/trading_service/main.py`:
- `POST /v1/trading/offers/sync` — trigger sync for a specific chain
- `GET /v1/trading/offers/sync-status` — get sync status for a chain

---

## B5: CLI Commands

Extend `cli/aitbc_cli/commands/trade.py`:
- `aitbc trade discover` — discover offers across chains
- `aitbc trade sync` — trigger sync for a specific chain
- `aitbc trade sync-status` — get sync status

Use Agent A's `OfferSyncClient` from A2.

---

## B6: Tests

`apps/trading/tests/test_v081_offer_sync.py` — tests for:
- Sync service polling loop
- Incremental sync
- Conflict resolution
- Staleness detection
- Discovery endpoint
- Sync endpoints
- CLI commands

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.8.1 — Cross-Chain Offer Synchronization
**Agent**: Agent B (Apps & Infrastructure)
