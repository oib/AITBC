# v0.10.15 — Agent Task Assignment

**Last Updated**: 2026-07-20
**Version**: 3.0 — Complete

**Release Theme**: Monolithic router/module decomposition across the stack.

**Goal**: Split the largest monolithic routers and modules into focused,
per-domain units while preserving public APIs, shared dependencies, and
passing tests.

> **Scope**: Decompose `sync.py`/`bridge.py` in the blockchain node,
> `main.py` in the trading service, and `developer_platform.py` in
coordinator-api, plus a production DEBUG guard.
> **Prerequisites**: [v0.10.14](../v0.10.14/change.log) (✅ complete).
> **Risk**: Low — pure refactor with preserved public APIs and passing tests.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent B** | `apps/blockchain-node/src/aitbc_chain/sync.py` + new `sync_*.py` modules | Decompose `sync.py` into `sync_validator.py`, `sync_bulk.py`, `sync_state.py`, `sync_block_import.py`; keep `sync.py` as thin `ChainSync` facade. |
| **Agent B** | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` + new `bridge_*.py` modules | Decompose `bridge.py` into `bridge_types.py`, `bridge_transfer.py`, `bridge_validator.py`, `bridge_finality.py`; keep `bridge.py` as thin `CrossChainBridge` facade. |
| **Agent B** | `apps/trading/src/trading_service/main.py` + new `trading_service/routers/*.py` | Decompose `main.py` into system, legacy_trading, transactions, exchange_compat, inter_chain, offers, subscriptions, settlement routers; add `dependencies.py` and `state.py`; keep `main.py` as thin app factory. |
| **Agent B** | `apps/coordinator-api/src/coordinator_api/contexts/developer_platform/routers/developer_platform.py` + new feature routers | Decompose `developer_platform.py` into `developers.py`, `bounties.py`, `certifications.py`, `hubs.py`, `staking.py`, `analytics.py`, `common.py`; keep `developer_platform.py` as thin aggregator. |

`sync.py` is a shared file (network layer); Agent B followed the coordination
protocol and completed the work sequentially.

---

## Verification Commands

```bash
# Lint (whole repo)
cd /opt/aitbc && ./venv/bin/python -m ruff check .

# Type check blockchain-node affected files
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes \
  apps/blockchain-node/src/aitbc_chain/sync.py \
  apps/blockchain-node/src/aitbc_chain/sync_validator.py \
  apps/blockchain-node/src/aitbc_chain/sync_bulk.py \
  apps/blockchain-node/src/aitbc_chain/sync_state.py \
  apps/blockchain-node/src/aitbc_chain/sync_block_import.py \
  apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py \
  apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_types.py \
  apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py \
  apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_validator.py \
  apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_finality.py

# Type check trading affected files
cd /opt/aitbc && ./venv/bin/python -m mypy --ignore-missing-imports \
  apps/trading/src/trading_service

# Type check coordinator-api developer platform affected files
cd /opt/aitbc && ./venv/bin/python -m mypy --ignore-missing-imports \
  apps/coordinator-api/src/coordinator_api/contexts/developer_platform

# Blockchain-node tests
cd /opt/aitbc/apps/blockchain-node && \
  PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""

# Trading tests
cd /opt/aitbc/apps/trading && \
  PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/trading/src ../../venv/bin/python -m pytest tests -q -o addopts=""

# Coordinator-api tests
cd /opt/aitbc/apps/coordinator-api && \
  PYTHONPATH=src ../../venv/bin/python -m pytest tests/test_main.py -q -o addopts=""
```

---

## Coordination

- **Agent B** decomposed `apps/blockchain-node/src/aitbc_chain/sync.py` (shared with network layer) using mixin modules; the `# WIP: Agent B` marker has been removed.
- **Agent B** decomposed `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` into mixin modules.
- **Agent B** decomposed `apps/trading/src/trading_service/main.py` into FastAPI routers with shared `dependencies.py` and `state.py`.
- **Agent B** decomposed `apps/coordinator-api/src/coordinator_api/contexts/developer_platform/routers/developer_platform.py` into feature routers with shared `common.py`.

---

## Notes

- All public imports are preserved via re-exports in the facade/aggregator modules.
- Blockchain-node mixin modules carry `# mypy: ignore-errors` while a typed base class for shared attributes is pending; see `docs/TYPE_CHECKING.md`.
- Production `DEBUG` guard added to `apps/coordinator-api/src/coordinator_api/config.py`.

*Generated with [Devin](https://devin.ai)*
