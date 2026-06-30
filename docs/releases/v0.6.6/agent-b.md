# v0.6.6 Compute Marketplace — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add config/settings to marketplace + GPU services, fix chain_id defaults, wire OfferFSM (A1) and BlockchainRPCClient (A2) into all three services, fix edge schema mismatches, add edge payment verification + marketplace advertising + coordinator health reporting, implement price-time priority matching with agent-coordinator integration, and write integration tests.

**Working directory**: `/opt/aitbc/apps/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/marketplace/tests/ apps/gpu/tests/ -q -o addopts="" --timeout=60
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/marketplace/ apps/gpu/ apps/edge/
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Marketplace config: add Settings class (fix 8006→8202, add DEFAULT_CHAIN_ID, AGENT_COORDINATOR_URL) | 🔴 P0 | `apps/marketplace/src/marketplace_service/config.py` (new), `main.py`, `services/marketplace_service.py` | ✅ |
| B2 | GPU service config: add Settings class, fix chain_id default (""→"ait-hub") | 🔴 P0 | `apps/gpu/src/gpu_service/config.py` (new), `main.py` | ✅ |
| B3 | Marketplace: use BlockchainRPCClient (A2) for offer queries, add chain_id filter, wire OfferFSM (A1) | 🔴 P0 | `apps/marketplace/src/marketplace_service/services/marketplace_service.py`, `domain/marketplace.py` | ✅ |
| B4 | GPU service: use BlockchainRPCClient (A2), fix chain_id default, wire OfferFSM (A1) into GPURegistry status | 🔴 P0 | `apps/gpu/src/gpu_service/main.py`, `domain/gpu_marketplace.py` | ✅ |
| B5 | Edge service: fix schema mismatches (GPUListing, ComputeResult), add payment verification, add marketplace advertising, add coordinator health reporting | 🔴 P0 | `apps/edge/src/aitbc_edge/schemas/gpu.py`, `schemas/serve.py`, `services/gpu_service.py`, `services/serve_service.py`, `routers/serve.py`, `config.py` | ✅ |
| B6 | Marketplace matching: price-time priority matching + agent-coordinator task queue integration | Medium | `apps/marketplace/src/marketplace_service/services/matching_service.py`, `main.py` | ✅ |
| B7 | Integration tests — offer lifecycle, chain_id routing, payment verification, matching | 🔴 P0 | `apps/marketplace/tests/test_v066_marketplace.py` (new), `apps/gpu/tests/test_v066_gpu.py` (new) | ✅ |
| B8 | Verify full test suite + ruff + mypy clean | High | — | ✅ |

---

## B1: Marketplace config

Create `apps/marketplace/src/marketplace_service/config.py`:
```python
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Marketplace service settings (v0.6.6)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow")

    # Blockchain integration
    blockchain_rpc_url: str = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
    default_chain_id: str = os.getenv("DEFAULT_CHAIN_ID", "ait-hub")

    # Agent coordinator integration (v0.6.6 matching → task queue)
    agent_coordinator_url: str = os.getenv("AGENT_COORDINATOR_URL", "http://localhost:8010")

    # Service binding
    marketplace_bind_host: str = os.getenv("MARKETPLACE_BIND_HOST", "0.0.0.0")
    marketplace_bind_port: int = int(os.getenv("MARKETPLACE_BIND_PORT", "8102"))


settings = Settings()
```

Update `main.py:19` to import from config: `from .config import settings` and replace `BLOCKCHAIN_RPC_URL = os.getenv(...)` with `settings.blockchain_rpc_url`.

Update `services/marketplace_service.py:208` to use `settings.blockchain_rpc_url` instead of `os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8006")`.

---

## B2: GPU service config

Create `apps/gpu/src/gpu_service/config.py`:
```python
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """GPU service settings (v0.6.6)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow")

    # Blockchain integration
    blockchain_rpc_url: str = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
    default_chain_id: str = os.getenv("DEFAULT_CHAIN_ID", "ait-hub")

    # Service binding
    gpu_bind_host: str = os.getenv("GPU_BIND_HOST", "0.0.0.0")
    gpu_bind_port: int = int(os.getenv("GPU_BIND_PORT", "8101"))


settings = Settings()
```

Update `main.py:280` to use `settings.default_chain_id` instead of `os.getenv("CHAIN_ID", "")`.

---

## B3: Marketplace integration

In `services/marketplace_service.py`:
- Import `BlockchainRPCClient` and `OfferFSM` from `aitbc.marketplace`
- Initialize `BlockchainRPCClient(settings.blockchain_rpc_url)` in service init
- Replace direct RPC calls with `BlockchainRPCClient.query_offers(chain_id=settings.default_chain_id)`
- Add chain_id filter to all offer queries
- Wire `OfferFSM` into offer lifecycle: when offer is created/updated, use `fsm.transition()` to validate state changes

---

## B4: GPU service integration

In `main.py` and `domain/gpu_marketplace.py`:
- Import `BlockchainRPCClient` and `OfferFSM` from `aitbc.marketplace`
- Initialize `BlockchainRPCClient(settings.blockchain_rpc_url)` in main
- Use `settings.default_chain_id` for all blockchain transactions
- Wire `OfferFSM` into `GPURegistry.status` field: replace string status with `OfferFSM` instance
- Use `BlockchainRPCClient.register_gpu()` and `allocate_gpu()` for blockchain operations

---

## B5: Edge service fixes

Fix schema mismatches:
- In `schemas/gpu.py`: align field names with `services/gpu_service.py` (use `gpu_id`, `model` instead of `listing_id`, `gpu_type`)
- In `schemas/serve.py`: align `result` field with `services/serve_service.py` (use `output_data` or update service to use `result`)
- Remove `# type: ignore[attr-defined]` comments after fixing

Add payment verification:
- In `routers/serve.py`: before serving, call `BlockchainRPCClient.verify_escrow(escrow_id)` to confirm payment
- Add feature flag `payment_verification_enabled` in config

Add marketplace advertising:
- Create endpoint `POST /v1/edge/capabilities` to advertise GPU models, capacity to marketplace
- Call marketplace RPC to register edge node capabilities

Add coordinator health reporting:
- Add periodic heartbeat to agent-coordinator `/health` endpoint
- Report edge node status (GPU availability, active tasks)

Remove dead code:
- Remove unused JWT config from `config.py` (lines 38-40)

---

## B6: Marketplace matching

In `services/matching_service.py`:
- Implement price-time priority matching: sort offers by (price, timestamp)
- Integrate with agent-coordinator: when match is found, submit task to `/tasks/submit`
- Add `agent_coordinator_url` to config (already in B1)
- Use `httpx.AsyncClient` to call agent-coordinator API

---

## B7: Integration tests

Create `apps/marketplace/tests/test_v066_marketplace.py`:
- `test_offer_lifecycle_with_fsm` — AVAILABLE → RESERVED → IN_USE → AVAILABLE
- `test_chain_id_filter_in_queries` — offers filtered by chain_id
- `test_price_time_matching` — offers sorted by price then time
- `test_agent_coordinator_task_submission` — match submits task to coordinator

Create `apps/gpu/tests/test_v066_gpu.py`:
- `test_gpu_registration_with_chain_id` — GPU registered with correct chain_id
- `test_gpu_offer_fsm_transitions` — GPU offer status follows FSM
- `test_gpu_allocation_on_blockchain` — allocation recorded on blockchain

---

## B8: Verify full test suite

Run full test suite for marketplace and GPU:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/marketplace/tests/ apps/gpu/tests/ -q -o addopts="" --timeout=60
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/marketplace/ apps/gpu/ apps/edge/
```

Verify all tests pass and ruff is clean.

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.6 — Compute Marketplace
**Agent**: Agent B (Apps & Infrastructure)
