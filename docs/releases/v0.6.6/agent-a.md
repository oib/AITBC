# v0.6.6 Compute Marketplace — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create (1) a formal offer state machine and (2) a shared blockchain RPC client with chain_id-aware offer queries. Both are consumed by Agent B's marketplace, GPU, and edge service integration.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/marketplace/ && ./venv/bin/python -m ruff check aitbc/marketplace/ tests/unit/test_offer_fsm.py tests/unit/test_blockchain_rpc.py && ./venv/bin/python -m pytest tests/unit/test_offer_fsm.py tests/unit/test_blockchain_rpc.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `OfferFSM` — formal offer state machine with validated transitions | 🔴 P0 | `aitbc/marketplace/offer_fsm.py` (new), `aitbc/marketplace/__init__.py` (new) | ✅ |
| A2 | Create `BlockchainRPCClient` — chain_id-aware blockchain RPC client for offer queries + tx submission | 🔴 P0 | `aitbc/marketplace/blockchain_rpc.py` (new), `aitbc/marketplace/__init__.py` (update) | ✅ |
| A3 | Unit tests for A1 + A2 + verify mypy/ruff/pytest clean | High | `tests/unit/test_offer_fsm.py`, `tests/unit/test_blockchain_rpc.py` | ✅ |

---

## A1: OfferFSM

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

---

## A2: BlockchainRPCClient

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

---

## A3: Unit tests

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

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.6 — Compute Marketplace
**Agent**: Agent A (Shared Core)
