# v0.6.5 Agent Coordination Service — Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Agent Coordination Service — Registration, Task Queues, Swarm Coordination, Workflow Execution, Blockchain Payment Integration.

**Goal**: Mature the agent-coordinator service into a production-ready coordination layer for AI agents. Add chain_id/island_id awareness to agent registration and task submission, implement blockchain payment escrow for task execution, and harden the service for production.

> **Scope constraint**: This release targets `apps/agent-coordinator/` (flat router structure, ~10K lines). The separate `apps/coordinator-api/` (bounded contexts) is NOT the target. This release does NOT add reputation scoring (v0.6.7), compute marketplace (v0.6.6), or bridge functionality (v0.7.0).

> **Prerequisites**: [v0.5.16](../v0.5.16/change.log) (chain_id-aware transaction submission — Bug 15/16 fixed), [v0.6.3](../v0.6.3/change.log) (Multi-Island Node Support), [v0.6.4](../v0.6.4/change.log) (Multi-Chain Per Island). v0.5.16 fixes verified in codebase. v0.6.4 in progress.

> **Risk**: Medium. Adding chain_id/island_id to models is backward compatible (optional fields). Payment escrow adds blockchain transaction overhead. Mitigated by: (1) optional chain_id (defaults to DEFAULT_CHAIN_ID), (2) payment escrow feature-flagged, (3) all changes in agent-coordinator app only.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (PaymentEscrow utility, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (agent-coordinator service integration)

---

## Quick Navigation

### Overview
- [Status Baseline](#status-baseline--verified-code-targets-from-subagent-investigation)
- [Already Fixed](#already-fixed-verified--no-work-needed)
- [Architecture: Agent Coordination with Chain Awareness](#architecture-agent-coordination-with-chain-awareness)
- [Task Split Overview](#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [PaymentEscrow](./agent-a.md#a1-paymentescrow)
- [Unit tests](./agent-a.md#a2-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Add config fields](./agent-b.md#b1-add-config-fields)
- [Add chain_id/island_id to agent models](./agent-b.md#b2-add-chain_idisland_id-to-agent-models)
- [Add chain_id/payment to task models](./agent-b.md#b3-add-chain_idpayment-to-task-models--escrow-integration)
- [Add chain_id to swarm + workflow models](./agent-b.md#b4-add-chain_id-to-swarm--workflow-models)
- [Make agent TTL configurable](./agent-b.md#b5-make-agent-ttl-configurable)
- [Integration tests](./agent-b.md#b6-integration-tests)
- [Verify full test suite](./agent-b.md#b7-verify-full-test-suite--mypy--ruff-clean)

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

---

## Architecture: Agent Coordination with Chain Awareness

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

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.5 — Agent Coordination Service
