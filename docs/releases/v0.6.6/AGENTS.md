# v0.6.6 — Agent Task Assignment

**Release Theme**: Compute Marketplace — GPU Offers, Edge Serving, Marketplace Matching, Blockchain-Backed Service Registration.

**Goal**: Connect the marketplace, GPU, and edge services into a functioning compute marketplace. Add chain_id awareness to offer discovery, implement a formal offer state machine, add payment verification to edge serving, and integrate marketplace matching with agent-coordinator task queues.

> **Scope constraint**: This release targets `apps/marketplace/` (~2K lines), `apps/gpu/` (~1.2K lines), `apps/edge/` (~1.4K lines), and new shared utilities in `aitbc/`. It does NOT add reputation scoring (v0.6.7), pool hub/mining (v0.6.7), or bridge functionality (v0.7.0).

> **Prerequisites**: [v0.6.5](../v0.6.5/change.log) (Agent Coordination — task assignment, PaymentEscrow), [v0.6.3](../v0.6.3/change.log) (Multi-Island), [v0.6.4](../v0.6.4/change.log) (Multi-Chain Per Island), [v0.5.16](../v0.5.16/change.log) (chain_id-aware transactions). All verified complete.

> **Risk**: Medium. Changes are backward compatible (optional chain_id, feature-flagged payment). Schema fixes in edge service are breaking but the existing code is already broken (runtime errors from schema mismatch). Mitigated by: (1) all offer FSM changes are additive, (2) payment verification is feature-flagged, (3) edge schema fixes fix already-broken code.

---

## Status Baseline — Verified Code Targets (from subagent investigation)

| Component | Location | Current State | v0.6.6 Target |
|-----------|----------|---------------|---------------|
| **Marketplace config** | `apps/marketplace/src/marketplace_service/main.py:19` | ❌ No Settings class, `BLOCKCHAIN_RPC_URL` defaults to `http://localhost:8006` (stale port) | Add Settings class, fix port to 8202, add `DEFAULT_CHAIN_ID`, `AGENT_COORDINATOR_URL` |
| **Marketplace RPC** | `apps/marketplace/src/marketplace_service/services/marketplace_service.py:206-276` | ✅ Uses RPC (not direct DB), but no chain_id in queries | Add chain_id filter to RPC queries |
| **Marketplace matching** | `apps/marketplace/src/marketplace_service/services/matching_service.py:21-98` | Basic scoring only, no agent-coordinator integration | Price-time priority matching + agent-coordinator task queue integration |
| **Marketplace offer FSM** | `apps/marketplace/src/marketplace_service/domain/marketplace.py` + `aitbc_shared/models/marketplace.py` | `status: str = "open"` — no enum, no transitions | Wire OfferFSM (A1) into offer lifecycle |
| **GPU service config** | `apps/gpu/src/gpu_service/main.py:280,298` | ❌ No Settings class, `chain_id` defaults to `""` (empty string), `BLOCKCHAIN_RPC_URL` defaults to 8202 (correct) | Add Settings class, fix chain_id default to `"ait-hub"` |
| **GPU service chain_id** | `apps/gpu/src/gpu_service/main.py:280` | `chain_id = transaction_data.get("chain_id") or os.getenv("CHAIN_ID", "")` — defaults to empty string | Default to `settings.default_chain_id` |
| **GPU offer model** | `apps/gpu/src/gpu_service/domain/gpu_marketplace.py:81-98` | `GPURegistry.status` = "available"/"booked"/"offline" — no FSM | Wire OfferFSM (A1) |
| **GPU tests** | `apps/gpu/tests/test_main.py` (46 lines) | Only 3 basic tests (health, status, profiles) | Add tests for chain_id, offer FSM, blockchain RPC |
| **Edge config** | `apps/edge/src/aitbc_edge/config.py:14-45` | ✅ Has Settings class (ServiceSettings subclass), `blockchain_rpc_port: 8202` (correct) | Add `MARKETPLACE_URL`, `AGENT_COORDINATOR_URL`, payment config |
| **Edge payment** | `apps/edge/src/aitbc_edge/routers/serve.py:27-33` | ❌ No payment verification before serving | Add payment verification (verify escrow on blockchain before serving) |
| **Edge GPU schema** | `apps/edge/src/aitbc_edge/schemas/gpu.py:11-36` vs `services/gpu_service.py:25-34` | ❌ **Schema mismatch**: schema has `listing_id`/`island_id`/`miner_id`/`gpu_type`, service code sets `gpu_id`/`model` — causes runtime errors | Fix schema to match service code, or fix service code to match schema |
| **Edge GPU fallback** | `apps/edge/src/aitbc_edge/services/gpu_service.py:54` | References `GPUListing.gpu_id` (nonexistent field) with `# type: ignore[attr-defined]` | Fix after schema fix |
| **Edge marketplace advertising** | — | ❌ No capability advertising to marketplace | Add edge node capability advertising (GPU models, capacity) |
| **Edge coordinator health** | — | ❌ No health reporting to agent-coordinator | Add heartbeat to agent-coordinator |
| **Edge ComputeResult schema** | `apps/edge/src/aitbc_edge/schemas/serve.py` vs `services/serve_service.py:111` | ❌ Schema has `result`, service references `output_data` | Fix schema mismatch |
| **Edge JWT config** | `apps/edge/src/aitbc_edge/config.py:38-40` | JWT settings defined but unused (dead code) | Either implement or remove (recommend: remove for now, add in v0.7.1) |
| **Blockchain GPU RPC** | `apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py` | ✅ `/gpus`, `/gpu/register`, `/gpu/info/{gpu_id}`, `/gpu/allocate` — all chain_id-aware | No change needed (consume from marketplace/gpu/edge) |
| **Blockchain TransactionRequest** | `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py:21-32` | ✅ Accepts `chain_id` (optional), validates against supported chains | No change needed |
| **Blockchain GPURegistration** | `apps/blockchain-node/src/aitbc_chain/state/gpu_resources.py:10-33` | ✅ Has `chain_id`, `gpu_id`, `model`, `region`, `price_per_hour`, `status` | No change needed |
| **Blockchain GPUAllocation** | `apps/blockchain-node/src/aitbc_chain/state/gpu_resources.py:35-55` | ✅ Has `chain_id`, `allocation_id`, `gpu_id`, `client_id`, `status` | No change needed |
| **Shared HTTP client** | `aitbc/network/client.py:318-615` | ✅ `AsyncAITBCHTTPClient` with retry, circuit breaker, rate limiting | Base for new BlockchainRPCClient (A2) |
| **Shared config base** | `packages/aitbc-shared/aitbc_shared/core/config.py` | ✅ `ServiceSettings`, `DatabaseConfig` | Marketplace + GPU should subclass these |
| **Shared offer model** | `packages/aitbc-shared/aitbc_shared/models/marketplace.py` | `MarketplaceOffer.status = "open"` — no enum | Add OfferStatus enum (in aitbc/, not aitbc_shared) |

### Already Fixed (verified — no work needed)

1. ✅ **Marketplace direct SQLite** (v0.5.16 Bugs 17-18) — `marketplace_service.py:206-276` now uses RPC via httpx to `BLOCKCHAIN_RPC_URL/rpc/transactions`
2. ✅ **GPU service chain_id** — `main.py:280` includes `chain_id` in `blockchain_tx` dict (but defaults to empty string — B2 fixes the default)
3. ✅ **Blockchain GPU RPC** — `/gpus`, `/gpu/register`, `/gpu/info`, `/gpu/allocate` all accept and filter by `chain_id`
4. ✅ **TransactionRequest chain_id** — accepts and validates `chain_id`
5. ✅ **Edge config** — already uses `ServiceSettings` subclass with `blockchain_rpc_port: 8202`

### Architecture: Compute Marketplace with Chain Awareness

```
┌──────────────────────────────────────────────────────────────────────┐
│ Compute Marketplace (v0.6.6)                                         │
│                                                                      │
│  GPU Service (apps/gpu/)                                             │
│    POST /v1/transactions → blockchain /rpc/transaction               │
│    - chain_id = settings.default_chain_id (NEW — was "")            │
│    - GPU offer registered on blockchain (GPU_REGISTER tx)            │
│    - Offer status tracked via OfferFSM (A1)                          │
│                                                                      │
│  Marketplace Service (apps/marketplace/)                             │
│    GET /v1/marketplace/offers → blockchain /rpc/gpus?chain_id=X     │
│    - chain_id filter in RPC queries (NEW)                            │
│    - MatchingService → agent-coordinator /tasks/submit (NEW)        │
│    - Offer lifecycle via OfferFSM (A1)                               │
│                                                                      │
│  Edge Service (apps/edge/)                                           │
│    POST /v1/serve/requests → verify payment on blockchain (NEW)     │
│    - Edge advertises capabilities to marketplace (NEW)               │
│    - Edge reports health to agent-coordinator (NEW)                  │
│    - Schema mismatches fixed (NEW)                                   │
│                                                                      │
│  Shared Core (aitbc/)                                                │
│    OfferFSM (A1) — available → reserved → in_use → available/delist  │
│    BlockchainRPCClient (A2) — wraps AsyncAITBCHTTPClient             │
│      - query_offers(chain_id, model, region, ...)                    │
│      - submit_transaction(chain_id, tx_data)                         │
│      - verify_escrow(escrow_id)                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 3 items | `aitbc/marketplace/offer_fsm.py` (new), `aitbc/marketplace/blockchain_rpc.py` (new), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `apps/marketplace/`, `apps/gpu/`, `apps/edge/`, `tests/` |

**Conflict boundary**: Agent A owns new `aitbc/marketplace/` utilities. Agent B owns all `apps/marketplace/`, `apps/gpu/`, `apps/edge/` files. Agent B consumes Agent A's utilities. No shared files are touched by both agents.

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Create (1) a formal offer state machine and (2) a shared blockchain RPC client with chain_id-aware offer queries. Both are consumed by Agent B's marketplace, GPU, and edge service integration.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/marketplace/ && ./venv/bin/python -m ruff check aitbc/marketplace/ tests/unit/test_offer_fsm.py tests/unit/test_blockchain_rpc.py && ./venv/bin/python -m pytest tests/unit/test_offer_fsm.py tests/unit/test_blockchain_rpc.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `OfferFSM` — formal offer state machine with validated transitions | 🔴 P0 | `aitbc/marketplace/offer_fsm.py` (new), `aitbc/marketplace/__init__.py` (new) | ✅ |
| A2 | Create `BlockchainRPCClient` — chain_id-aware blockchain RPC client for offer queries + tx submission | 🔴 P0 | `aitbc/marketplace/blockchain_rpc.py` (new), `aitbc/marketplace/__init__.py` (update) | ✅ |
| A3 | Unit tests for A1 + A2 + verify mypy/ruff/pytest clean | High | `tests/unit/test_offer_fsm.py`, `tests/unit/test_blockchain_rpc.py` | ✅ |

### Agent A — Detailed Instructions

#### A1: OfferFSM

Create `aitbc/marketplace/__init__.py` (empty) and `aitbc/marketplace/offer_fsm.py`:

```python
from __future__ import annotations

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class OfferStatus(StrEnum):
    """Lifecycle states for a compute/GPU offer."""
    AVAILABLE = "available"     # Offer is listed and bookable
    RESERVED = "reserved"       # Offer is matched/locked for a consumer
    IN_USE = "in_use"           # Offer is actively being used (compute running)
    DELISTED = "delisted"       # Offer is permanently removed by provider
    EXPIRED = "expired"         # Offer timed out without being used


# Valid state transitions: {current_status: set_of_allowed_next_statuses}
_TRANSITIONS: dict[OfferStatus, set[OfferStatus]] = {
    OfferStatus.AVAILABLE: {OfferStatus.RESERVED, OfferStatus.DELISTED, OfferStatus.EXPIRED},
    OfferStatus.RESERVED: {OfferStatus.IN_USE, OfferStatus.AVAILABLE, OfferStatus.EXPIRED},
    OfferStatus.IN_USE: {OfferStatus.AVAILABLE, OfferStatus.DELISTED},
    OfferStatus.DELISTED: set(),   # terminal
    OfferStatus.EXPIRED: set(),    # terminal
}


class OfferFSM:
    """Finite state machine for offer lifecycle.

    Validates state transitions and rejects invalid ones.
    Terminal states (DELISTED, EXPIRED) cannot transition further.
    """

    def __init__(self, initial_status: OfferStatus = OfferStatus.AVAILABLE) -> None:
        self._status = initial_status

    @property
    def status(self) -> OfferStatus:
        return self._status

    def can_transition(self, new_status: OfferStatus) -> bool:
        return new_status in _TRANSITIONS.get(self._status, set())

    def transition(self, new_status: OfferStatus) -> OfferStatus:
        if not self.can_transition(new_status):
            raise ValueError(
                f"Invalid offer transition: {self._status.value} → {new_status.value}"
            )
        old = self._status
        self._status = new_status
        logger.info("Offer transitioned: %s → %s", old.value, new_status.value)
        return self._status

    def is_terminal(self) -> bool:
        return len(_TRANSITIONS.get(self._status, set())) == 0

    @staticmethod
    def valid_transitions(status: OfferStatus) -> set[OfferStatus]:
        return _TRANSITIONS.get(status, set()).copy()

    @staticmethod
    def from_string(status: str) -> OfferStatus:
        try:
            return OfferStatus(status)
        except ValueError as e:
            raise ValueError(f"Unknown offer status: '{status}'") from e
```

Export from `aitbc/marketplace/__init__.py`:
```python
from .offer_fsm import OfferFSM, OfferStatus

__all__ = ["OfferFSM", "OfferStatus"]
```

#### A2: BlockchainRPCClient

Create `aitbc/marketplace/blockchain_rpc.py`:

```python
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BlockchainRPCClient:
    """Chain-aware blockchain RPC client for marketplace operations.

    Wraps httpx.AsyncClient with chain_id-aware methods for:
    - Querying GPU offers from the blockchain
    - Submitting transactions with chain_id
    - Verifying escrow status

    This is a thin client — retry/circuit-breaker is handled by the caller
    or by AsyncAITBCHTTPClient if wired in. For v0.6.6 we use httpx directly
    to keep the dependency surface minimal.
    """

    def __init__(self, rpc_url: str = "http://localhost:8202", timeout: float = 10.0) -> None:
        self._rpc_url = rpc_url.rstrip("/")
        self._timeout = timeout

    @property
    def rpc_url(self) -> str:
        return self._rpc_url

    async def query_offers(
        self,
        chain_id: str | None = None,
        status: str | None = None,
        gpu_model: str | None = None,
        region: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Query GPU offers from blockchain.

        Calls GET /rpc/gpus with optional chain_id, status, model, region filters.
        Returns list of offer dicts.
        """
        params: dict[str, Any] = {"limit": limit}
        if chain_id:
            params["chain_id"] = chain_id
        if status:
            params["status"] = status
        # gpu_model and region are not yet supported as RPC query params
        # on the blockchain side — we filter client-side for now.
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._rpc_url}/rpc/gpus", params=params)
            resp.raise_for_status()
            data = resp.json()
            offers = data.get("gpus", data) if isinstance(data, dict) else data
            if not isinstance(offers, list):
                offers = []
        # Client-side filter for gpu_model and region (until blockchain RPC supports them)
        if gpu_model:
            offers = [o for o in offers if gpu_model.lower() in str(o.get("model", "")).lower()]
        if region:
            offers = [o for o in offers if region.lower() in str(o.get("region", "")).lower()]
        return offers

    async def get_offer(self, gpu_id: str, chain_id: str | None = None) -> dict[str, Any] | None:
        """Get a single GPU offer by ID."""
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._rpc_url}/rpc/gpu/info/{gpu_id}", params=params)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def submit_transaction(self, tx_data: dict[str, Any]) -> dict[str, Any]:
        """Submit a transaction to the blockchain.

        The tx_data must include chain_id. Calls POST /rpc/transaction.
        Returns the blockchain response dict.
        """
        if not tx_data.get("chain_id"):
            raise ValueError("tx_data must include 'chain_id'")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._rpc_url}/rpc/transaction", json=tx_data)
            resp.raise_for_status()
            return resp.json()

    async def verify_escrow(self, escrow_id: str) -> dict[str, Any] | None:
        """Verify escrow status on blockchain.

        Calls GET /rpc/escrow/{escrow_id} (if available) or returns None.
        For v0.6.6, escrow verification uses the agent-coordinator's escrow endpoint
        — this method is a placeholder for direct blockchain escrow verification.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._rpc_url}/rpc/escrow/{escrow_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def register_gpu(self, registration_data: dict[str, Any]) -> dict[str, Any]:
        """Register a GPU on the blockchain.

        Calls POST /rpc/gpu/register. The registration_data must include chain_id.
        """
        if not registration_data.get("chain_id"):
            raise ValueError("registration_data must include 'chain_id'")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._rpc_url}/rpc/gpu/register", json=registration_data)
            resp.raise_for_status()
            return resp.json()

    async def allocate_gpu(self, allocation_data: dict[str, Any]) -> dict[str, Any]:
        """Allocate a GPU on the blockchain (record a booking).

        Calls POST /rpc/gpu/allocate. The allocation_data must include chain_id.
        """
        if not allocation_data.get("chain_id"):
            raise ValueError("allocation_data must include 'chain_id'")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._rpc_url}/rpc/gpu/allocate", json=allocation_data)
            resp.raise_for_status()
            return resp.json()
```

Update `aitbc/marketplace/__init__.py`:
```python
from .blockchain_rpc import BlockchainRPCClient
from .offer_fsm import OfferFSM, OfferStatus

__all__ = ["BlockchainRPCClient", "OfferFSM", "OfferStatus"]
```

#### A3: Unit tests

**`tests/unit/test_offer_fsm.py`**:
- `test_initial_status` — default is AVAILABLE
- `test_valid_transition_available_to_reserved` — AVAILABLE → RESERVED
- `test_valid_transition_reserved_to_in_use` — RESERVED → IN_USE
- `test_valid_transition_in_use_to_available` — IN_USE → AVAILABLE
- `test_valid_transition_reserved_to_available` — RESERVED → AVAILABLE (release)
- `test_valid_transition_available_to_delisted` — AVAILABLE → DELISTED
- `test_invalid_transition_available_to_in_use` — AVAILABLE → IN_USE raises
- `test_invalid_transition_delisted_to_anything` — terminal state raises
- `test_invalid_transition_expired_to_anything` — terminal state raises
- `test_is_terminal_delisted` — DELISTED is terminal
- `test_is_terminal_expired` — EXPIRED is terminal
- `test_is_terminal_not_available` — AVAILABLE is not terminal
- `test_can_transition` — returns True/False without raising
- `test_valid_transitions_static` — returns allowed next states
- `test_from_string_valid` — "available" → OfferStatus.AVAILABLE
- `test_from_string_invalid_raises` — "unknown" raises ValueError

**`tests/unit/test_blockchain_rpc.py`** (mock httpx with respx or unittest.mock.AsyncMock):
- `test_query_offers_with_chain_id` — verifies chain_id in request params
- `test_query_offers_without_chain_id` — no chain_id param when None
- `test_query_offers_client_side_filter_gpu_model` — filters by model
- `test_query_offers_client_side_filter_region` — filters by region
- `test_get_offer_found` — returns offer dict
- `test_get_offer_not_found` — returns None on 404
- `test_submit_transaction_with_chain_id` — submits successfully
- `test_submit_transaction_without_chain_id_raises` — raises ValueError
- `test_register_gpu_with_chain_id` — registers successfully
- `test_register_gpu_without_chain_id_raises` — raises ValueError
- `test_allocate_gpu_with_chain_id` — allocates successfully
- `test_allocate_gpu_without_chain_id_raises` — raises ValueError
- `test_verify_escrow_found` — returns escrow dict
- `test_verify_escrow_not_found` — returns None on 404
- `test_rpc_url_strips_trailing_slash` — "http://localhost:8202/" → "http://localhost:8202"

---

## Agent B — Apps & Infrastructure

**Scope**: Add config/settings to marketplace + GPU services, fix chain_id defaults, wire OfferFSM (A1) and BlockchainRPCClient (A2) into all three services, fix edge schema mismatches, add edge payment verification + marketplace advertising + coordinator health reporting, implement price-time priority matching with agent-coordinator integration, and write integration tests.

**Working directory**: `/opt/aitbc/apps/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/marketplace/tests/ apps/gpu/tests/ -q -o addopts="" --timeout=60
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/marketplace/ apps/gpu/ apps/edge/
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Marketplace config: add Settings class (fix 8006→8202, add DEFAULT_CHAIN_ID, AGENT_COORDINATOR_URL) | 🔴 P0 | `apps/marketplace/src/marketplace_service/config.py` (new), `main.py`, `services/marketplace_service.py` | ✅ |
| B2 | GPU service config: add Settings class, fix chain_id default (""→"ait-hub") | 🔴 P0 | `apps/gpu/src/gpu_service/config.py` (new), `main.py` | ✅ |
| B3 | Marketplace: use BlockchainRPCClient (A2) for offer queries, add chain_id filter, wire OfferFSM (A1) | 🔴 P0 | `apps/marketplace/src/marketplace_service/services/marketplace_service.py`, `domain/marketplace.py` | ⬜ |
| B4 | GPU service: use BlockchainRPCClient (A2), fix chain_id default, wire OfferFSM (A1) into GPURegistry status | 🔴 P0 | `apps/gpu/src/gpu_service/main.py`, `domain/gpu_marketplace.py` | ⬜ |
| B5 | Edge service: fix schema mismatches (GPUListing, ComputeResult), add payment verification, add marketplace advertising, add coordinator health reporting | 🔴 P0 | `apps/edge/src/aitbc_edge/schemas/gpu.py`, `schemas/serve.py`, `services/gpu_service.py`, `services/serve_service.py`, `routers/serve.py`, `config.py` | ⬜ |
| B6 | Marketplace matching: price-time priority matching + agent-coordinator task queue integration | Medium | `apps/marketplace/src/marketplace_service/services/matching_service.py`, `main.py` | ⬜ |
| B7 | Integration tests — offer lifecycle, chain_id routing, payment verification, matching | 🔴 P0 | `apps/marketplace/tests/test_v066_marketplace.py` (new), `apps/gpu/tests/test_v066_gpu.py` (new) | ⬜ |
| B8 | Verify full test suite + ruff + mypy clean | High | — | ⬜ |

### Agent B — Detailed Instructions

#### B1: Marketplace config

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

#### B2: GPU service config

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

Update `main.py:298` to use `settings.blockchain_rpc_url` instead of `os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")`.

#### B3: Marketplace — BlockchainRPCClient + OfferFSM integration

In `services/marketplace_service.py`:
- Replace the direct httpx call (lines 206-276) with `BlockchainRPCClient.query_offers(chain_id=...)`.
- Import: `from aitbc.marketplace import BlockchainRPCClient, OfferFSM, OfferStatus`.
- Initialize the client in `__init__` or as a module-level singleton.
- Add `chain_id` parameter to `list_offers()` method signature.
- Pass `chain_id` to `query_offers()`.

In `domain/marketplace.py`:
- Add `chain_id: str | None = Field(None, index=True)` to `MarketplaceOffer` (via aitbc_shared or local override).
- Wire `OfferFSM` into `update_offer_status()`: validate transitions using `OfferFSM.from_string(current_status).transition(OfferFSM.from_string(new_status))`.

#### B4: GPU service — BlockchainRPCClient + OfferFSM

In `main.py`:
- Import `from aitbc.marketplace import BlockchainRPCClient, OfferFSM, OfferStatus`.
- Replace direct httpx blockchain calls with `BlockchainRPCClient` methods.
- Use `BlockchainRPCClient.register_gpu()` for GPU registration.
- Use `BlockchainRPCClient.submit_transaction()` for transaction submission.

In `domain/gpu_marketplace.py`:
- Map `GPURegistry.status` values to `OfferStatus`:
  - "available" → `OfferStatus.AVAILABLE`
  - "booked" → `OfferStatus.RESERVED` (or `IN_USE` depending on context)
  - "offline" → `OfferStatus.DELISTED`
- Add `chain_id: str = Field(default="ait-hub", index=True)` to `GPURegistry`.
- Validate status transitions using `OfferFSM` in the update endpoint.

#### B5: Edge service — schema fixes + payment + advertising + health

**Schema fixes** (🔴 P0 — these are already-broken code):

1. `schemas/gpu.py` — fix `GPUListing` to match service code. Add fields: `gpu_id: str = Field(index=True)`, `model: str = Field(default="Unknown", index=True)`. Keep `listing_id`, `island_id`, `miner_id`, `gpu_type` but make them optional with defaults. Remove `# type: ignore[attr-defined]` from `services/gpu_service.py` after fix.

2. `schemas/serve.py` — fix `ComputeResult` to match service code. Add `output_data: dict[str, Any] = Field(default_factory=dict)` alongside or instead of `result`.

**Payment verification** (🔴 P0):

In `routers/serve.py` — update `submit_compute_request`:
```python
@router.post("/requests")
async def submit_compute_request(request: SubmitComputeRequest) -> dict[str, Any]:
    # v0.6.6: verify payment before serving
    if settings.require_payment_verification:
        from aitbc.marketplace import BlockchainRPCClient
        rpc_client = BlockchainRPCClient(rpc_url=settings.blockchain_rpc_url)
        escrow = await rpc_client.verify_escrow(request.escrow_id)
        if not escrow or escrow.get("status") != "locked":
            raise HTTPException(status_code=402, detail="Payment required: escrow not locked")
    # ... existing serving logic ...
```

Add to `SubmitComputeRequest`: `escrow_id: str | None = None`.

Add to `config.py` Settings: `require_payment_verification: bool = False`.

**Marketplace advertising** (Medium):

In `services/gpu_service.py` — add `advertise_to_marketplace()` method:
```python
async def advertise_to_marketplace(self) -> dict[str, Any]:
    """Advertise this edge node's GPU capabilities to the marketplace."""
    # POST to marketplace service with GPU capabilities
    ...
```

Add `MARKETPLACE_URL` to edge config.

**Coordinator health reporting** (Medium):

In `main.py` lifespan — add periodic heartbeat to agent-coordinator:
```python
async def report_health():
    while True:
        # POST to agent-coordinator /agents/heartbeat
        await asyncio.sleep(settings.agent_heartbeat_interval_seconds)
```

Add `AGENT_COORDINATOR_URL` and `agent_heartbeat_interval_seconds: int = 60` to edge config.

**Remove unused JWT config** (Low):
Remove `jwt_secret_key`, `jwt_algorithm`, `jwt_expiration_hours` from `config.py` (dead code — not implemented anywhere). Add a comment: `# JWT auth deferred to v0.7.1 (Bridge Security)`.

#### B6: Marketplace matching — price-time priority + agent-coordinator integration

In `services/matching_service.py`:
- Implement price-time priority: sort offers by price (ascending), then by registration time (oldest first).
- Add `match_and_assign()` method that:
  1. Finds best match via `find_best_match()`
  2. Reserves the offer via `OfferFSM.transition(OfferStatus.RESERVED)`
  3. Submits a task to agent-coordinator via `POST {AGENT_COORDINATOR_URL}/tasks/submit` with `chain_id` and `payment` fields
  4. Returns the match + task_id + escrow_id

In `main.py` — add endpoint:
```python
@router.post("/v1/marketplace/match")
async def match_request(request: MatchRequest) -> dict[str, Any]:
    """Match a compute request to the best available GPU offer."""
    match = await matching_service.match_and_assign(
        request.requirements,
        request.max_price,
        request.preferred_region,
        chain_id=request.chain_id,
    )
    return {"status": "success", "match": match}
```

#### B7: Integration tests

**`apps/marketplace/tests/test_v066_marketplace.py`**:
1. `test_offer_fsm_available_to_reserved` — OfferFSM transition
2. `test_offer_fsm_invalid_transition_raises` — AVAILABLE → IN_USE raises
3. `test_marketplace_config_blockchain_rpc_url` — config field exists, defaults to 8202
4. `test_marketplace_config_default_chain_id` — config field exists
5. `test_marketplace_config_agent_coordinator_url` — config field exists
6. `test_blockchain_rpc_client_query_offers` — mock RPC, verify chain_id in params
7. `test_blockchain_rpc_client_submit_transaction` — mock RPC, verify chain_id required
8. `test_marketplace_list_offers_with_chain_id` — offers filtered by chain_id
9. `test_matching_service_find_best_match` — basic matching
10. `test_matching_service_price_time_priority` — lower price wins
11. `test_matching_service_match_and_assign` — match → reserve → task submit

**`apps/gpu/tests/test_v066_gpu.py`**:
1. `test_gpu_config_default_chain_id` — config field exists, defaults to "ait-hub"
2. `test_gpu_config_blockchain_rpc_url` — config field exists, defaults to 8202
3. `test_gpu_registry_has_chain_id` — GPURegistry model has chain_id field
4. `test_gpu_offer_fsm_integration` — status transitions validated
5. `test_gpu_register_includes_chain_id` — registration tx includes chain_id

#### B8: Verify full test suite

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
# Expected: 270+ passed (253 existing + 30 new A1-A3 tests)

cd /opt/aitbc && ./venv/bin/python -m pytest apps/marketplace/tests/ apps/gpu/tests/ -q -o addopts="" --timeout=60
# Expected: All pass (existing + new B7 tests)

cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/marketplace/
# Expected: 0 errors

cd /opt/aitbc && ./venv/bin/python -m ruff check .
# Expected: All checks passed
```

---

## Dependency Graph

```
Phase 1 (parallel):
  A1: OfferFSM ─────────────────────────┐
  A2: BlockchainRPCClient ──────────────┤
  A3: Unit tests for A1 + A2 ───────────┘
                                        │
Phase 2 (sequential, depends on A1+A2):
  B1: Marketplace config ───────────────┐
  B2: GPU service config ───────────────┤
                                        │
Phase 3 (depends on B1+B2+A1+A2):
  B3: Marketplace RPC + FSM ────────────┤
  B4: GPU service RPC + FSM ────────────┤
  B5: Edge service fixes ───────────────┤ (independent of B3/B4)
                                        │
Phase 4 (depends on B3):
  B6: Marketplace matching ─────────────┤
                                        │
Phase 5 (depends on all):
  B7: Integration tests ────────────────┤
  B8: Final verification ───────────────┘
```

---

## Coordination

- **Agent A** goes first (Phase 1) — creates `OfferFSM` and `BlockchainRPCClient` in `aitbc/marketplace/`.
- **Agent B** starts Phase 2 after Agent A's Phase 1 is complete (B3/B4 need `BlockchainRPCClient` + `OfferFSM`).
- **B5** (edge service) is independent of B3/B4 and can proceed in parallel with Phase 3.
- **B3 and B4** both consume A1+A2 but modify different files (marketplace vs GPU) — no conflict.
- No shared files are touched by both agents.

---

## Success Criteria

- ✅ OfferFSM validates offer state transitions (available → reserved → in_use → available/delist)
- ✅ BlockchainRPCClient provides chain_id-aware offer queries + tx submission
- ✅ Marketplace uses BlockchainRPCClient (not raw httpx) with chain_id filter
- ✅ GPU service defaults chain_id to "ait-hub" (not empty string)
- ✅ GPU service uses BlockchainRPCClient for blockchain interactions
- ✅ Edge service schema mismatches fixed (GPUListing, ComputeResult)
- ✅ Edge service verifies payment before serving (feature-flagged)
- ✅ Edge service advertises capabilities to marketplace
- ✅ Edge service reports health to agent-coordinator
- ✅ Marketplace matching integrates with agent-coordinator task queues
- ✅ Marketplace config uses port 8202 (not stale 8006)
- ✅ All existing tests pass (253 unit + 70 agent-coordinator + marketplace + gpu)
- ✅ New tests pass (30 A1-A3 unit + 16 B7 integration)
