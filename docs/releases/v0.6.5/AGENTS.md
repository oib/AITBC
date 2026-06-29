# v0.6.5 — Agent Task Assignment

**Release Theme**: Agent Coordination Service — Registration, Task Queues, Swarm Coordination, Workflow Execution, Blockchain Payment Integration.

**Goal**: Mature the agent-coordinator service into a production-ready coordination layer for AI agents. Add chain_id/island_id awareness to agent registration and task submission, implement blockchain payment escrow for task execution, and harden the service for production.

> **Scope constraint**: This release targets `apps/agent-coordinator/` (flat router structure, ~10K lines). The separate `apps/coordinator-api/` (bounded contexts) is NOT the target. This release does NOT add reputation scoring (v0.6.7), compute marketplace (v0.6.6), or bridge functionality (v0.7.0).

> **Prerequisites**: [v0.5.16](../v0.5.16/change.log) (chain_id-aware transaction submission — Bug 15/16 fixed), [v0.6.3](../v0.6.3/change.log) (Multi-Island Node Support), [v0.6.4](../v0.6.4/change.log) (Multi-Chain Per Island). v0.5.16 fixes verified in codebase. v0.6.4 in progress.

> **Risk**: Medium. Adding chain_id/island_id to models is backward compatible (optional fields). Payment escrow adds blockchain transaction overhead. Mitigated by: (1) optional chain_id (defaults to DEFAULT_CHAIN_ID), (2) payment escrow feature-flagged, (3) all changes in agent-coordinator app only.

---

## Status Baseline — Verified Code Targets (from subagent investigation)

| Component | Location | Current State | v0.6.5 Target |
|-----------|----------|---------------|---------------|
| **AgentRegistrationRequest** | `apps/agent-coordinator/src/app/models.py:6` | No chain_id, no island_id | Add `chain_id`, `island_id` (optional) |
| **AgentInfo** | `apps/agent-coordinator/src/app/routing/agent_discovery.py:53` | No chain_id, no island_id | Add `chain_id`, `island_id` fields |
| **Agent discovery** | `apps/agent-coordinator/src/app/routers/agents.py:52` | Filters by agent_type + capabilities only | Add chain_id/island_id filter |
| **TaskSubmission** | `apps/agent-coordinator/src/app/models.py:18` | No chain_id, no payment | Add `chain_id`, `payment` fields |
| **TaskDistributor** | `apps/agent-coordinator/src/app/routing/load_balancer.py:469` | No chain awareness, no payment | Add per-chain queues, payment escrow hooks |
| **coin_requests** | `apps/agent-coordinator/src/app/routers/coin_requests.py:35` | ✅ chain_id included (v0.5.16 fix) | No change needed |
| **agent_stream.py** | `apps/agent-coordinator/src/app/websocket/agent_stream.py:361` | ✅ Port 8006, chain_id included (v0.5.16 fix) | No change needed |
| **TransactionService** | `aitbc/crypto/transaction_service.py:143` | ✅ chain_id in signed tx dict | No change needed |
| **Swarm endpoints** | `apps/agent-coordinator/src/app/routers/swarm.py` | No chain_id/island_id in models | Add chain_id to swarm models |
| **Workflow endpoints** | `apps/agent-coordinator/src/app/routers/workflow.py` | No chain_id in models | Add chain_id to workflow models |
| **Config — BLOCKCHAIN_RPC_URL** | `agent_stream.py:361` (env var only) | ❌ Not in Settings class | Add to `config.py` Settings |
| **Config — DEFAULT_CHAIN_ID** | — | ❌ Does not exist | Add to `config.py` Settings |
| **Config — DEFAULT_ISLAND_ID** | — | ❌ Does not exist | Add to `config.py` Settings |
| **Config — escrow/TTL** | — | ❌ Does not exist | Add escrow + agent TTL config |
| **Agent TTL** | `agent_discovery.py:111` | Hardcoded `max_heartbeat_age=120` | Make configurable |
| **Agent cleanup** | `agent_discovery.py:110` | `cleanup_interval=60` hardcoded | Make configurable |

### Already Fixed (verified — no work needed)

1. ✅ **Bug 15: Port 8202 → 8006** — `agent_stream.py:361` uses `os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8006")`
2. ✅ **Bug 16: chain_id in transaction** — `agent_stream.py:364-366` includes chain_id in transaction body
3. ✅ **TransactionService chain_id** — `transaction_service.py:143` includes chain_id in signed transaction dict

### Architecture: Agent Coordination with Chain Awareness

```
┌──────────────────────────────────────────────────────────────────┐
│ Agent Coordinator (apps/agent-coordinator/)                      │
│                                                                  │
│ Agent Registration:                                              │
│   POST /agents/register                                         │
│   - agent_id, agent_type, capabilities, services, endpoints     │
│   - chain_id (NEW — which chain agent operates on)              │
│   - island_id (NEW — which island agent is on)                  │
│                                                                  │
│ Agent Discovery:                                                 │
│   POST /agents/discover                                         │
│   - Filter by agent_type, capabilities (existing)               │
│   - Filter by chain_id, island_id (NEW)                         │
│                                                                  │
│ Task Submission:                                                 │
│   POST /tasks/submit                                            │
│   - task_data, priority, requirements (existing)                │
│   - chain_id (NEW — which chain to execute on)                  │
│   - payment (NEW — {amount, fee} for task execution)            │
│                                                                  │
│ Payment Escrow:                                                  │
│   1. Task submitted → lock payment on blockchain (escrow)       │
│   2. Task completed → release payment to agent                  │
│   3. Task timeout → refund payment to requester                 │
│                                                                  │
│ Backward compat: no chain_id → defaults to DEFAULT_CHAIN_ID     │
│                  no payment → task runs without escrow          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 2 items | `aitbc/crypto/payment_escrow.py` (new), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 7 items | `apps/agent-coordinator/` (config, models, routers, routing), `tests/` |

**Conflict boundary**: Agent A owns new `aitbc/` utilities. Agent B owns all `apps/agent-coordinator/` files. Agent B consumes Agent A's utilities.

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Create a reusable payment escrow utility for blockchain-based fund locking/releasing. This is blockchain-agnostic and will be consumed by Agent B's task payment integration.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/crypto/payment_escrow.py aitbc/crypto/__init__.py && ./venv/bin/python -m ruff check aitbc/crypto/payment_escrow.py aitbc/crypto/__init__.py tests/unit/test_payment_escrow.py && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `PaymentEscrow` — lock/release/refund funds via blockchain transactions | 🔴 P0 | `aitbc/crypto/payment_escrow.py` (new), `aitbc/crypto/__init__.py` (update) | ⬜ |
| A2 | Unit tests for A1 + verify mypy/ruff/pytest clean | High | `tests/unit/test_payment_escrow.py` | ⬜ |

### Agent A — Detailed Instructions

#### A1: PaymentEscrow

Create `aitbc/crypto/payment_escrow.py`:

```python
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EscrowStatus(str, Enum):
    """Status of a payment escrow."""
    PENDING = "pending"       # Escrow created, not yet locked on-chain
    LOCKED = "locked"         # Funds locked on blockchain
    RELEASED = "released"     # Funds released to agent (task completed)
    REFUNDED = "refunded"     # Funds refunded to requester (task failed/timeout)
    EXPIRED = "expired"       # Escrow expired without completion


@dataclass
class EscrowEntry:
    """A single payment escrow entry."""
    escrow_id: str
    task_id: str
    chain_id: str
    requester: str            # Address paying for the task
    agent: str                # Address receiving payment
    amount: int               # Payment amount (in smallest units)
    fee: int = 0              # Transaction fee
    status: EscrowStatus = EscrowStatus.PENDING
    created_at: float = field(default_factory=time.time)
    locked_at: float | None = None
    released_at: float | None = None
    expires_at: float | None = None  # Timeout timestamp
    tx_hash_lock: str | None = None   # Blockchain tx hash for lock
    tx_hash_release: str | None = None  # Blockchain tx hash for release
    tx_hash_refund: str | None = None   # Blockchain tx hash for refund
    metadata: dict[str, Any] = field(default_factory=dict)


class PaymentEscrow:
    """Manages payment escrows for task execution.

    Provides in-memory tracking of escrow entries with hooks for
    blockchain transaction submission (lock/release/refund).

    The actual blockchain transaction submission is delegated to a
    callback function provided by the caller (Agent B wires this to
    the blockchain RPC client).
    """

    def __init__(
        self,
        lock_callback: Callable[[str, str, str, int], str] | None = None,
        release_callback: Callable[[str, str, str, int], str] | None = None,
        refund_callback: Callable[[str, str, str, int], str] | None = None,
        default_timeout: float = 3600.0,
    ) -> None:
        """Initialize the payment escrow manager.

        Args:
            lock_callback: Called to lock funds on-chain.
                Args: (chain_id, from_addr, to_addr, amount). Returns tx_hash.
            release_callback: Called to release funds to agent.
                Args: (chain_id, from_addr, to_addr, amount). Returns tx_hash.
            refund_callback: Called to refund funds to requester.
                Args: (chain_id, from_addr, to_addr, amount). Returns tx_hash.
            default_timeout: Default escrow timeout in seconds (default 3600).
        """
        self._escrows: dict[str, EscrowEntry] = {}
        self._lock_callback = lock_callback
        self._release_callback = release_callback
        self._refund_callback = refund_callback
        self._default_timeout = default_timeout

    def create_escrow(
        self,
        task_id: str,
        chain_id: str,
        requester: str,
        agent: str,
        amount: int,
        fee: int = 0,
        timeout: float | None = None,
    ) -> EscrowEntry:
        """Create a new payment escrow entry.

        Returns the created EscrowEntry. Does NOT lock funds yet —
        call lock() to submit the lock transaction.
        """
        if amount <= 0:
            raise ValueError(f"Escrow amount must be positive, got {amount}")
        escrow_id = str(uuid.uuid4())
        expires_at = time.time() + (timeout or self._default_timeout)
        entry = EscrowEntry(
            escrow_id=escrow_id,
            task_id=task_id,
            chain_id=chain_id,
            requester=requester,
            agent=agent,
            amount=amount,
            fee=fee,
            expires_at=expires_at,
        )
        self._escrows[escrow_id] = entry
        logger.info("Created escrow %s for task %s (amount=%d, chain=%s)", escrow_id, task_id, amount, chain_id)
        return entry

    def lock(self, escrow_id: str) -> EscrowEntry:
        """Lock funds on-chain for an escrow.

        Calls the lock_callback to submit a blockchain transaction.
        Raises ValueError if escrow not found or not in PENDING status.
        """
        entry = self._get_entry(escrow_id)
        if entry.status != EscrowStatus.PENDING:
            raise ValueError(f"Escrow {escrow_id} is not pending (status={entry.status})")
        if self._lock_callback:
            entry.tx_hash_lock = self._lock_callback(entry.chain_id, entry.requester, entry.agent, entry.amount)
        entry.status = EscrowStatus.LOCKED
        entry.locked_at = time.time()
        logger.info("Locked escrow %s (tx=%s)", escrow_id, entry.tx_hash_lock)
        return entry

    def release(self, escrow_id: str) -> EscrowEntry:
        """Release funds to agent on task completion.

        Calls the release_callback to submit a blockchain transaction.
        Raises ValueError if escrow not found or not in LOCKED status.
        """
        entry = self._get_entry(escrow_id)
        if entry.status != EscrowStatus.LOCKED:
            raise ValueError(f"Escrow {escrow_id} is not locked (status={entry.status})")
        if self._release_callback:
            entry.tx_hash_release = self._release_callback(entry.chain_id, entry.requester, entry.agent, entry.amount)
        entry.status = EscrowStatus.RELEASED
        entry.released_at = time.time()
        logger.info("Released escrow %s (tx=%s)", escrow_id, entry.tx_hash_release)
        return entry

    def refund(self, escrow_id: str) -> EscrowEntry:
        """Refund funds to requester on task failure/timeout.

        Calls the refund_callback to submit a blockchain transaction.
        Raises ValueError if escrow not found or not in LOCKED status.
        """
        entry = self._get_entry(escrow_id)
        if entry.status != EscrowStatus.LOCKED:
            raise ValueError(f"Escrow {escrow_id} is not locked (status={entry.status})")
        if self._refund_callback:
            entry.tx_hash_refund = self._refund_callback(entry.chain_id, entry.agent, entry.requester, entry.amount)
        entry.status = EscrowStatus.REFUNDED
        logger.info("Refunded escrow %s (tx=%s)", escrow_id, entry.tx_hash_refund)
        return entry

    def expire_stale(self) -> list[EscrowEntry]:
        """Expire and refund all escrows that have passed their timeout.

        Returns list of expired/refunded entries.
        """
        now = time.time()
        expired: list[EscrowEntry] = []
        for entry in self._escrows.values():
            if entry.status == EscrowStatus.LOCKED and entry.expires_at and now > entry.expires_at:
                try:
                    self.refund(entry.escrow_id)
                    expired.append(entry)
                except Exception as e:
                    logger.error("Failed to refund expired escrow %s: %s", entry.escrow_id, e)
                    entry.status = EscrowStatus.EXPIRED
                    expired.append(entry)
        return expired

    def get_escrow(self, escrow_id: str) -> EscrowEntry | None:
        """Get an escrow entry by ID."""
        return self._escrows.get(escrow_id)

    def get_escrow_for_task(self, task_id: str) -> EscrowEntry | None:
        """Get the escrow entry for a task."""
        for entry in self._escrows.values():
            if entry.task_id == task_id:
                return entry
        return None

    def get_all_escrows(self) -> list[EscrowEntry]:
        """Return all escrow entries."""
        return list(self._escrows.values())

    def get_escrows_by_status(self, status: EscrowStatus) -> list[EscrowEntry]:
        """Return all escrows with a given status."""
        return [e for e in self._escrows.values() if e.status == status]

    def _get_entry(self, escrow_id: str) -> EscrowEntry:
        """Get an escrow entry or raise ValueError."""
        entry = self._escrows.get(escrow_id)
        if entry is None:
            raise ValueError(f"Escrow {escrow_id} not found")
        return entry
```

Export from `aitbc/crypto/__init__.py` as `PaymentEscrow`, `EscrowEntry`, `EscrowStatus` (add to existing exports).

**Note**: The `Callable` type hint requires `from typing import Callable` — add it to the imports.

#### A2: Unit tests

**`tests/unit/test_payment_escrow.py`**:
- `test_create_escrow` — create escrow, verify fields
- `test_create_escrow_zero_amount_raises` — amount <= 0 raises ValueError
- `test_lock_pending_escrow` — lock changes status to LOCKED
- `test_lock_non_pending_raises` — locking a non-pending escrow raises
- `test_lock_unknown_raises` — locking unknown escrow raises
- `test_release_locked_escrow` — release changes status to RELEASED
- `test_release_non_locked_raises` — releasing non-locked escrow raises
- `test_refund_locked_escrow` — refund changes status to REFUNDED
- `test_refund_non_locked_raises` — refunding non-locked escrow raises
- `test_lock_callback_called` — verify lock_callback is called with correct args
- `test_release_callback_called` — verify release_callback is called
- `test_refund_callback_called` — verify refund_callback is called
- `test_no_callback_still_works` — lock/release/refund without callbacks (no tx hash)
- `test_expire_stale_refunds` — expired escrows are refunded
- `test_expire_stale_no_locked` — no LOCKED escrows → empty list
- `test_get_escrow` — lookup by escrow_id
- `test_get_escrow_for_task` — lookup by task_id
- `test_get_escrows_by_status` — filter by status
- `test_get_all_escrows` — returns all entries
- `test_default_timeout` — escrow expires after default_timeout

---

## Agent B — Apps & Infrastructure

**Scope**: Add chain_id/island_id to agent and task models, implement blockchain payment escrow integration, add config fields, and write integration tests.

**Working directory**: `/opt/aitbc/apps/agent-coordinator/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/agent-coordinator/tests/ -q -o addopts="" --timeout=60
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add config fields: `BLOCKCHAIN_RPC_URL`, `DEFAULT_CHAIN_ID`, `DEFAULT_ISLAND_ID`, escrow/TTL config | 🔴 P0 | `apps/agent-coordinator/src/app/config.py` | ⬜ |
| B2 | Add `chain_id`, `island_id` to `AgentRegistrationRequest` + `AgentInfo` + agent discovery filters | 🔴 P0 | `apps/agent-coordinator/src/app/models.py`, `routing/agent_discovery.py`, `routers/agents.py` | ⬜ |
| B3 | Add `chain_id`, `payment` to `TaskSubmission` + wire `PaymentEscrow` (A1) to task lifecycle | 🔴 P0 | `apps/agent-coordinator/src/app/models.py`, `routers/tasks.py`, `routing/load_balancer.py` | ⬜ |
| B4 | Add `chain_id` to swarm + workflow models | Medium | `apps/agent-coordinator/src/app/routers/swarm.py`, `routers/workflow.py` | ⬜ |
| B5 | Make agent TTL configurable (remove hardcoded 120s/60s) | Medium | `apps/agent-coordinator/src/app/routing/agent_discovery.py` | ⬜ |
| B6 | Integration tests — agent registration with chain_id, task payment escrow, backward compat | 🔴 P0 | `apps/agent-coordinator/tests/test_v065_agent_coordination.py` (new) | ⬜ |
| B7 | Verify full test suite + mypy + ruff clean | High | — | ⬜ |

### Agent B — Detailed Instructions

#### B1: Add config fields

In `apps/agent-coordinator/src/app/config.py`, add to `Settings` class:

```python
# Blockchain integration (v0.6.5)
blockchain_rpc_url: str = "http://localhost:8006"
default_chain_id: str = "ait-hub"
default_island_id: str = ""

# Task payment escrow (v0.6.5)
task_payment_escrow_enabled: bool = False
task_payment_timeout_seconds: float = 3600.0
task_max_retries: int = 3

# Agent TTL (v0.6.5)
agent_heartbeat_timeout_seconds: int = 120
agent_cleanup_interval_seconds: int = 60
```

**Note**: `BLOCKCHAIN_RPC_URL` is already read via `os.getenv()` in `agent_stream.py:361`. Adding it to `Settings` makes it properly managed. The env var reading in `agent_stream.py` can stay as fallback or be updated to use `settings.blockchain_rpc_url`.

#### B2: Add chain_id/island_id to agent models

**`apps/agent-coordinator/src/app/models.py`** — update `AgentRegistrationRequest` (line 6):
```python
class AgentRegistrationRequest(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(..., description="Type of agent")
    capabilities: list[str] = Field(default_factory=list, description="Agent capabilities")
    services: list[str] = Field(default_factory=list, description="Available services")
    endpoints: dict[str, str] = Field(default_factory=dict, description="Service endpoints")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    # v0.6.5: chain/island awareness
    chain_id: str | None = Field(None, description="Chain ID this agent operates on")
    island_id: str | None = Field(None, description="Island ID this agent is on")
```

**`apps/agent-coordinator/src/app/routing/agent_discovery.py`** — update `AgentInfo` (line 53):
```python
@dataclass
class AgentInfo:
    # ... existing fields ...
    # v0.6.5: chain/island awareness
    chain_id: str = ""
    island_id: str = ""
```

Update `to_dict()` (line 70) to include `chain_id` and `island_id`.
Update `from_dict()` (line 88) to parse `chain_id` and `island_id`.

Update `create_agent_info()` in `routers/agents.py` (line 25) to pass `chain_id` and `island_id` from the request.

Update `discover_agents()` filter logic in `agent_discovery.py` (around line 198) to filter by `chain_id` and `island_id`:
```python
if "chain_id" in query:
    chain_id = query["chain_id"]
    candidate_agents = [a for a in candidate_agents if a.chain_id == chain_id]
if "island_id" in query:
    island_id = query["island_id"]
    candidate_agents = [a for a in candidate_agents if a.island_id == island_id]
```

#### B3: Add chain_id/payment to task models + escrow integration

**`apps/agent-coordinator/src/app/models.py`** — update `TaskSubmission` (line 18):
```python
class TaskSubmission(BaseModel):
    task_data: dict[str, Any] = Field(..., description="Task data")
    priority: str = Field("normal", description="Task priority")
    requirements: dict[str, Any] | None = Field(None, description="Task requirements")
    # v0.6.5: chain awareness + payment
    chain_id: str | None = Field(None, description="Chain ID to execute task on")
    payment: TaskPayment | None = Field(None, description="Payment for task execution")


class TaskPayment(BaseModel):
    """Payment details for task execution escrow."""
    amount: int = Field(..., description="Payment amount in smallest units")
    fee: int = Field(0, description="Transaction fee")
    requester: str = Field(..., description="Requester address (pays for task)")
    agent: str = Field(..., description="Agent address (receives payment)")
    timeout_seconds: float = Field(3600.0, description="Escrow timeout")
```

**`apps/agent-coordinator/src/app/routers/tasks.py`** — update `submit_task` (line 18):
```python
from aitbc.crypto import PaymentEscrow, EscrowStatus

@router.post("/tasks/submit")
@rate_limit(rate=50, per=60)
async def submit_task(request_http: Request, request: TaskSubmission, background_tasks: BackgroundTasks) -> dict[str, Any]:
    # ... existing validation ...
    chain_id = request.chain_id or settings.default_chain_id

    # Create payment escrow if payment provided and escrow enabled
    escrow_id = None
    if request.payment and settings.task_payment_escrow_enabled:
        escrow = state.payment_escrow.create_escrow(
            task_id=task_id,
            chain_id=chain_id,
            requester=request.payment.requester,
            agent=request.payment.agent,
            amount=request.payment.amount,
            fee=request.payment.fee,
            timeout=request.payment.timeout_seconds,
        )
        state.payment_escrow.lock(escrow.escrow_id)
        escrow_id = escrow.escrow_id

    await state.task_distributor.submit_task(request.task_data, priority, request.requirements)
    return {
        "status": "success",
        "task_id": task_id,
        "chain_id": chain_id,
        "escrow_id": escrow_id,
        # ... existing fields ...
    }
```

Add `payment_escrow` to `state.py`:
```python
# state.py
from aitbc.crypto import PaymentEscrow
payment_escrow: PaymentEscrow | None = None
```

Initialize in app startup with blockchain callbacks (wired to `TransactionService`).

#### B4: Add chain_id to swarm + workflow models

**`apps/agent-coordinator/src/app/routers/swarm.py`** — add `chain_id` to `JoinRequest` (line 25) and `CoordinateRequest` (line 34):
```python
class JoinRequest(BaseModel):
    role: str
    capability: str
    priority: str
    region: str | None = None
    chain_id: str | None = None  # v0.6.5

class CoordinateRequest(BaseModel):
    task: str
    collaborators: int
    strategy: str
    timeout_seconds: int
    chain_id: str | None = None  # v0.6.5
```

**`apps/agent-coordinator/src/app/routers/workflow.py`** — add `chain_id` to `CreateWorkflowRequest` (line 21) and `ExecuteWorkflowRequest` (line 30):
```python
class CreateWorkflowRequest(BaseModel):
    # ... existing fields ...
    chain_id: str | None = None  # v0.6.5

class ExecuteWorkflowRequest(BaseModel):
    # ... existing fields ...
    chain_id: str | None = None  # v0.6.5
```

#### B5: Make agent TTL configurable

In `apps/agent-coordinator/src/app/routing/agent_discovery.py`, update `AgentRegistry.__init__` (line 102):
```python
def __init__(self, redis_url: str = "redis://localhost:6379/1") -> None:
    self.redis_url = redis_url
    self.redis_client: Any = None
    self.agents: dict[str, AgentInfo] = {}
    self.service_index: dict[str, set[str]] = {}
    self.capability_index: dict[str, set[str]] = {}
    self.type_index: dict[AgentType, set[str]] = {}
    # v0.6.5: configurable TTL (was hardcoded 30/60/120)
    from ..config import settings
    self.heartbeat_interval = 30
    self.cleanup_interval = settings.agent_cleanup_interval_seconds
    self.max_heartbeat_age = settings.agent_heartbeat_timeout_seconds
```

#### B6: Integration tests

Create `apps/agent-coordinator/tests/test_v065_agent_coordination.py`:

**Test cases**:
1. `test_agent_registration_with_chain_id` — register agent with chain_id, verify stored
2. `test_agent_registration_without_chain_id_backward_compat` — register without chain_id, verify no crash
3. `test_agent_discovery_filter_by_chain` — discover agents filtered by chain_id
4. `test_agent_discovery_filter_by_island` — discover agents filtered by island_id
5. `test_task_submission_with_payment` — submit task with payment, verify escrow created
6. `test_task_submission_without_payment_backward_compat` — submit without payment, verify no escrow
7. `test_task_submission_with_chain_id` — submit task with chain_id, verify stored
8. `test_payment_escrow_lock_release` — escrow lock → task complete → release
9. `test_payment_escrow_lock_refund` — escrow lock → task fails → refund
10. `test_payment_escrow_timeout` — escrow expires → auto-refund
11. `test_swarm_join_with_chain_id` — join swarm with chain_id
12. `test_workflow_create_with_chain_id` — create workflow with chain_id
13. `test_config_blockchain_rpc_url` — verify config field exists
14. `test_config_default_chain_id` — verify config field exists

#### B7: Verify full test suite

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
# Expected: 270+ passed (230 existing + 40 new A1-A2 tests)

cd /opt/aitbc && ./venv/bin/python -m pytest apps/agent-coordinator/tests/ -q -o addopts="" --timeout=60
# Expected: All pass (existing + new B6 tests)

cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/
# Expected: 0 errors

cd /opt/aitbc && ./venv/bin/python -m ruff check .
# Expected: All checks passed
```

---

## Dependency Graph

```
Phase 1 (parallel):
  A1: PaymentEscrow ───────────────┐
  A2: Unit tests for A1 ───────────┘
                                   │
Phase 2 (sequential, depends on A1):
  B1: Config fields ───────────────┐
  B2: Agent chain_id/island_id ────┤
  B3: Task chain_id + escrow ──────┤ (needs A1 PaymentEscrow)
                                   │
Phase 3 (depends on B1):           │
  B4: Swarm/workflow chain_id ─────┤
  B5: Agent TTL configurable ──────┤
                                   │
Phase 4 (depends on all):          │
  B6: Integration tests ───────────┤
  B7: Final verification ──────────┘
```

---

## Coordination

- **Agent A** goes first (Phase 1) — creates `PaymentEscrow` in `aitbc/crypto/`.
- **Agent B** starts Phase 2 after Agent A's Phase 1 is complete (B3 needs `PaymentEscrow`).
- **B2 and B3** both modify `models.py` — sequence them (B2 first, then B3).
- **B4 and B5** are independent of each other and can be done in parallel after B1.

---

## Success Criteria

- ✅ Agents register with chain_id and are discoverable by chain
- ✅ Tasks submitted with chain_id and payment, funds locked on blockchain
- ✅ Task completion releases payment to agent
- ✅ Task timeout refunds payment to requester
- ✅ Swarm coordination includes chain_id awareness
- ✅ Workflow execution includes chain_id awareness
- ✅ Coin request sends correct chain_id (already fixed in v0.5.16)
- ✅ Agent TTL is configurable (not hardcoded)
- ✅ Backward compatible: no chain_id → defaults to DEFAULT_CHAIN_ID
- ✅ Backward compatible: no payment → task runs without escrow
- ✅ All existing tests pass (230 unit + 2 agent-coordinator)
- ✅ New tests pass (payment escrow + agent coordination integration)
- ✅ mypy: 0 errors
- ✅ ruff: clean
