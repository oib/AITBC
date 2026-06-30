# v0.6.5 Agent Coordination Service — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add chain_id/island_id to agent and task models, implement blockchain payment escrow integration, add config fields, and write integration tests.

**Working directory**: `/opt/aitbc/apps/agent-coordinator/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/agent-coordinator/tests/ -q -o addopts="" --timeout=60
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add config fields: `BLOCKCHAIN_RPC_URL`, `DEFAULT_CHAIN_ID`, `DEFAULT_ISLAND_ID`, escrow/TTL config | 🔴 P0 | `apps/agent-coordinator/src/app/config.py` | ✅ |
| B2 | Add `chain_id`, `island_id` to `AgentRegistrationRequest` + `AgentInfo` + agent discovery filters | 🔴 P0 | `apps/agent-coordinator/src/app/models.py`, `routing/agent_discovery.py`, `routers/agents.py` | ✅ |
| B3 | Add `chain_id`, `payment` to `TaskSubmission` + wire `PaymentEscrow` (A1) to task lifecycle | 🔴 P0 | `apps/agent-coordinator/src/app/models.py`, `routers/tasks.py`, `routing/load_balancer.py` | ✅ |
| B4 | Add `chain_id` to swarm + workflow models | Medium | `apps/agent-coordinator/src/app/routers/swarm.py`, `routers/workflow.py` | ✅ |
| B5 | Make agent TTL configurable (remove hardcoded 120s/60s) | Medium | `apps/agent-coordinator/src/app/routing/agent_discovery.py` | ✅ |
| B6 | Integration tests — agent registration with chain_id, task payment escrow, backward compat | 🔴 P0 | `apps/agent-coordinator/tests/test_v065_agent_coordination.py` (new) | ✅ |
| B7 | Verify full test suite + mypy + ruff clean | High | — | ✅ |

---

## B1: Add config fields

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

---

## B2: Add chain_id/island_id to agent models

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

---

## B3: Add chain_id/payment to task models + escrow integration

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
```

In `routers/tasks.py`:
- Import `PaymentEscrow` from `aitbc.crypto.payment_escrow`
- Initialize `PaymentEscrow` with blockchain RPC callbacks
- In task submission, if `payment` is present and `task_payment_escrow_enabled=True`:
  - Create escrow via `payment_escrow.create_escrow()`
  - Lock funds via `payment_escrow.lock()`
  - Store escrow_id with task
- On task completion, release payment via `payment_escrow.release()`
- On task timeout, refund via `payment_escrow.refund()`

In `routing/load_balancer.py`:
- Add per-chain task queues (optional for v0.6.5, can defer to v0.6.6)
- Pass chain_id to agent selection logic

---

## B4: Add chain_id to swarm + workflow models

In `routers/swarm.py`:
- Add `chain_id` field to swarm models
- Update swarm creation/lookup to filter by chain_id

In `routers/workflow.py`:
- Add `chain_id` field to workflow models
- Update workflow execution to use chain_id for blockchain transactions

---

## B5: Make agent TTL configurable

In `routing/agent_discovery.py`:
- Replace hardcoded `max_heartbeat_age=120` with `settings.agent_heartbeat_timeout_seconds`
- Replace hardcoded `cleanup_interval=60` with `settings.agent_cleanup_interval_seconds`

---

## B6: Integration tests

Create `apps/agent-coordinator/tests/test_v065_agent_coordination.py`:
- `test_agent_registration_with_chain_id` — register agent with chain_id, verify stored
- `test_agent_discovery_filters_by_chain_id` — discover agents filtered by chain_id
- `test_agent_discovery_filters_by_island_id` — discover agents filtered by island_id
- `test_task_submission_with_chain_id` — submit task with chain_id
- `test_task_payment_escrow_enabled` — task with payment creates escrow
- `test_task_payment_escrow_disabled` — task with payment skips escrow when disabled
- `test_task_completion_releases_payment` — task completion releases escrow
- `test_task_timeout_refunds_payment` — task timeout refunds escrow
- `test_backward_compat_no_chain_id` — tasks without chain_id use default
- `test_backward_compat_no_payment` — tasks without payment run without escrow

---

## B7: Verify full test suite

Run full test suite for agent-coordinator:
```bash
cd /opt/aitbc && ./venv/bin/python -m pytest apps/agent-coordinator/tests/ -q -o addopts="" --timeout=60
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes apps/agent-coordinator/src/
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/agent-coordinator/
```

Verify all tests pass and mypy/ruff are clean.

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.5 — Agent Coordination Service
**Agent**: Agent B (Apps & Infrastructure)
