# v0.13.0 — Mature Autonomous Economic Infrastructure

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Mature the OpenClaw Autonomous Economics layer into a
production-grade, self-regulating system: automated staking and rebalancing,
performance-bond lifecycle, provider reinvestment, risk/solvency engine,
cross-chain yield, and slashing appeals.

**Prerequisites**: v0.10.18 complete; v0.11.0 in-flight, v0.12.0 planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/agent_economics/`, `aitbc/wallet/`, `aitbc/risk/` | Staking/rebalancing strategies, bond lifecycle models, risk/solvency engine |
| **Agent B** | `apps/coordinator-api` marketplace/governance, `apps/miner/`, `apps/gpu/`, `cli/` | Bond eligibility, reinvestment loop, yield adapters, slashing appeals, CLI |

---

## Agent A — Shared Core & Types

### A1: Automated staking & rebalancing (P0)

- File: `aitbc/agent_economics/staking.py` (new)
  - `StakingStrategy`, `Delegation`, `DelegationStatus`, `YieldPosition`, and
    delegation/unbond/withdraw/claim helpers.
- File: `aitbc/agent_economics/rebalancing.py` (new or update)
  - `RebalancingTrigger` enum (threshold, schedule, opportunity) added to
    `ReinvestmentPolicy`; cross-chain rebalancing triggers and exposure limits.
- File: `aitbc/agent_economics/portfolio.py` (new)
  - `Portfolio` aggregate over `ChainHoldings` with allocation, deviation,
    and rebalance-needed detection.

### A2: Performance bond lifecycle (P0)

- File: `aitbc/agent_economics/bonds.py` (updated)
  - `PerformanceBond` with lock, top-up, partial release, full release, slash,
    and liquidation states.
- File: `aitbc/agent_economics/liquidation.py` (new)
  - `LiquidationReason`, `LiquidationEvent`, `LiquidationStatus`,
    `ProviderOffboarding`, `OffboardingStatus`, `liquidate_bond`, and
    `offboard_provider` helpers.

### A3: Risk & solvency engine (P1)

- File: `aitbc/risk/__init__.py` (new)
  - Module exports.
- File: `aitbc/risk/errors.py` (new)
  - `RiskError`.
- File: `aitbc/risk/scoring.py` (new)
  - `RiskCategory`, `RiskLevel`, `RiskScore`, and configurable `RiskScorer`
    with weighted `assess` and aggregate helpers.
- File: `aitbc/risk/solvency.py` (new)
  - `SolvencyReport` and `SolvencyEngine` for bond shortfall prediction,
    buffered collateral requirements, and action recommendations.
- File: `aitbc/risk/circuit_breaker.py` (new)
  - `CircuitState`, `MarketStressEvent`, `CircuitBreaker` with CLOSED/OPEN/
    HALF_OPEN state machine and `is_open()` helper.

### A4: Cross-chain yield & liquidity (P2)

- File: `aitbc/agent_economics/yield_venues.py` (new)
  - Pluggable yield-venue adapters.
- File: `aitbc/agent_economics/swaps.py` (new)
  - Cross-chain AITBC swap abstractions.

---

## Agent B — Applications, Marketplace & CLI

### B1: Provider eligibility & bond lifecycle (P0) — ✅ complete

- File: `apps/coordinator-api/src/coordinator_api/contexts/marketplace/domain/provider_bond.py` (new)
  - `ProviderBond` SQLModel and `ProviderBondStatus` enum; `is_provider_eligible` and `set_provider_bond_status` helpers.
- File: `apps/coordinator-api/alembic/versions/79e94b77d6bd_add_provider_bond_and_slash_appeal_.py` (new)
  - Creates `provider_bond` table and indexes.
- File: `apps/coordinator-api/src/coordinator_api/main.py`
  - Imports `ProviderBond` so `SQLModel.metadata` and `alembic check` agree.

### B2: Provider reinvestment loop (P1) — ✅ complete

- File: `apps/miner/miner_app/reinvestment.py`
  - Existing `ReinvestmentEngine` converts earnings to staking/capacity actions.
- File: `apps/miner/miner_app/worker.py` (new in v0.12.0, updated)
  - `ReinvestmentWorker` polls earnings and best-effort triggers GPU capacity publish.
- File: `apps/gpu/src/gpu_app/capacity_publisher.py` (new)
  - `publish_capacity` posts updated provider capacity to the coordinator marketplace API.
- File: `apps/gpu/src/gpu_app/__init__.py` (new)
  - Package marker for `gpu_app`.

### B3: Cross-chain yield integrations (P2) — ✅ complete

- File: `apps/coordinator-api/src/coordinator_api/contexts/agent_economics/yield_adapter.py` (new)
  - `YieldAdapter` abstract base, `_YieldRegistry`, `yield_registry`, and `DemoStakingAdapter`.
- File: `apps/coordinator-api/src/coordinator_api/contexts/agent_economics/__init__.py` (new)
  - Package marker for the `agent_economics` context.
- File: `scripts/economics/harvest_yield.py` (new)
  - CLI runner for harvesting/compounding yield from registered venues (dry-run capable).

### B4: Slashing appeals & governance (P2) — ✅ complete

- File: `apps/coordinator-api/src/coordinator_api/contexts/governance/domain/slash_appeal.py` (new)
  - SQLModel `SlashAppeal` and `SlashAppealStatus` evidence workflow.
- File: `apps/coordinator-api/alembic/versions/79e94b77d6bd_add_provider_bond_and_slash_appeal_.py` (new)
  - Creates `slash_appeal` table and indexes.
- File: `cli/aitbc_cli/commands/bond.py` (new)
  - `bond top-up`, `bond status`, `bond appeal` (simulated when no coordinator URL is configured).
- File: `cli/aitbc_cli/commands/reinvest.py` (new)
  - `reinvest policy` and `reinvest simulate` using the `miner_app` engine.
- File: `cli/aitbc_cli/core/main.py`
  - Registers `bond` and `reinvest` command groups.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""

# Coordinator-api migrations
cd apps/coordinator-api
PYTHONPATH=src:/opt/aitbc DATABASE_URL=sqlite:////tmp/aitbc-v13.db \
  /opt/aitbc/venv/bin/alembic upgrade head
PYTHONPATH=src:/opt/aitbc DATABASE_URL=sqlite:////tmp/aitbc-v13.db \
  /opt/aitbc/venv/bin/alembic check
```

## Coordination Protocol

- Agent A owns `aitbc/agent_economics/` and `aitbc/risk/` shared types and
  engines.
- Agent B owns `apps/coordinator-api` marketplace/governance integrations,
  `apps/miner/` and `apps/gpu/` reinvestment wiring, and CLI commands.
- Shared boundary: `aitbc/agent_economics/bonds.py` and
  `aitbc/risk/solvency.py` are consumed by the `apps/coordinator-api`
  marketplace; Agent A writes them first, then Agent B wires eligibility.
- Sequence: Agent A lands staking, bond, and risk primitives before Agent B
  begins marketplace and reinvestment integration.

## Release Gate

- [x] Automated staking and rebalancing strategies have unit tests.
- [x] Performance bond lifecycle (lock, top-up, release, liquidation) is
      modeled and tested.
- [x] Provider reinvestment loop publishes updated capacity.
- [x] Risk/solvency engine triggers circuit breakers under simulated stress.
- [x] Cross-chain yield and slashing appeal workflows are testable.
- [x] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
