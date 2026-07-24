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

- File: `aitbc/risk/solvency.py` (new)
  - Bond shortfall prediction and action recommendations.
- File: `aitbc/risk/circuit_breaker.py` (new)
  - Market-stress circuit breakers for autonomous actions.
- File: `aitbc/risk/scoring.py` (new)
  - Risk scoring for chains, validators, and storage providers.

### A4: Cross-chain yield & liquidity (P2)

- File: `aitbc/agent_economics/yield_venues.py` (new)
  - Pluggable yield-venue adapters.
- File: `aitbc/agent_economics/swaps.py` (new)
  - Cross-chain AITBC swap abstractions.

---

## Agent B — Applications, Marketplace & CLI

### B1: Provider eligibility & bond lifecycle (P0)

- File: `apps/coordinator-api/src/coordinator_api/contexts/marketplace/provider_bond.py` (new)
  - Bond status to provider eligibility mapping.
- File: `apps/coordinator-api/alembic/versions/` (new migration)
  - Add `provider_bond_status` columns to provider tables.

### B2: Provider reinvestment loop (P1)

- File: `apps/miner/src/miner_app/reinvestment.py` (new or update)
  - Autonomous reinvestment of earned AITBC into GPU/storage capacity.
- File: `apps/gpu/src/gpu_app/capacity_publisher.py` (TBD)
  - Publish updated capacity after reinvestment.

### B3: Cross-chain yield integrations (P2)

- File: `apps/coordinator-api/src/coordinator_api/contexts/agent_economics/yield_adapter.py` (new)
  - Yield-venue adapter registry and API.
- File: `scripts/economics/harvest_yield.py` (new)
  - Yield harvest and compounding runner.

### B4: Slashing appeals & governance (P2)

- File: `apps/coordinator-api/src/coordinator_api/contexts/governance/domain/slash_appeal.py` (new)
  - SQLModel `SlashAppeal` and evidence workflow.
- File: `cli/aitbc_cli/commands/bond.py` (new)
  - `bond top-up`, `bond status`, `bond appeal`.
- File: `cli/aitbc_cli/commands/reinvest.py` (new)
  - `reinvest policy`, `reinvest simulate`.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
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
- [ ] Provider reinvestment loop publishes updated capacity.
- [ ] Risk/solvency engine triggers circuit breakers under simulated stress.
- [ ] Cross-chain yield and slashing appeal workflows are testable.
- [ ] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
