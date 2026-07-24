# v0.12.0 — OpenClaw Autonomous Economics

**Last Updated**: 2026-07-24
**Version**: 1.0 — Complete ✅

**Release Theme**: Implement the OpenClaw Autonomous Economics layer:
self-managing agent wallets, automated staking and rebalancing, performance
bonds, dynamic fee markets, and provider reinvestment loops.

**Prerequisites**: v0.10.18 complete; v0.11.0 in-flight.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/agent_economics/`, `aitbc/wallet/`, shared types | Economic primitives, wallet/escrow types, bond/stake models, rebalancing and pricing policies |
| **Agent B** | `apps/coordinator-api` governance/economic domains, `cli/`, `apps/miner/` | DAO governance API, CLI commands, provider reinvestment loop, pricing integration, eventing/audit |

---

## Agent A — Shared Core & Types

### A1: Agent wallets & escrow (P0)

- File: `aitbc/wallet/__init__.py` (new)
- File: `aitbc/wallet/agent_wallet.py` (new)
  - `AgentWallet` and `WalletStatus` with per-token balances and validated
    deposit/withdraw/transfer operations.
- File: `aitbc/wallet/escrow.py` (new)
  - `Escrow`, `EscrowAllowance`, and `EscrowStatus` primitives for lease,
    storage, and compute payments.
- File: `aitbc/wallet/errors.py` (new)
  - `WalletError`, `AgentWalletError`, `InsufficientBalanceError`,
    `EscrowError`, and `AllowanceExceededError`.

### A2: Performance bonds & staking (P0)

- File: `aitbc/agent_economics/bonds.py` (new)
  - `PerformanceBond` with `BondStatus` lifecycle (pending, active, locked,
    slashed, released, liquidated, expired) and `StakeAccount` with
    `StakeStatus` lifecycle (pending, active, unstaking, unstaked).
- File: `aitbc/agent_economics/slash.py` (new)
  - `SlashReason`, `SlashingCondition`, `SlashEvent`, `compute_slash_amount`,
    `validate_slash_event`, `slash_bond`, and `slash_stake` validators.

### A3: Rebalancing & reinvestment policies (P1)

- File: `aitbc/agent_economics/rebalance.py` (new)
  - `ReinvestmentPolicy`, `ChainHoldings`, `RebalanceConstraint`,
    `RebalanceAction`, and `Rebalancer` planner.

### A4: Dynamic fee market strategies (P1)

- File: `aitbc/agent_economics/pricing.py` (new)
  - `MarketMakerStrategy` with bid/ask spread and inventory adjustment.
  - `DemandForecast` and `DemandTrend` primitives.
  - `SurgePricing` with demand-driven multiplier updates.
  - `DynamicFeeMarket` combining surge pricing and demand forecasts.

---

## Agent B — Applications, DAO & CLI

### B1: OpenClaw DAO economic governance (P2) — ✅ complete

- File: `apps/coordinator-api/src/coordinator_api/contexts/governance/domain/economic_proposal.py` (new)
  - SQLModel `EconomicParameterProposal`.
- File: `apps/coordinator-api/src/coordinator_api/main.py`
  - Import `EconomicParameterProposal` so `SQLModel.metadata` and `alembic check` agree.
- File: `apps/coordinator-api/alembic/versions/bf44ceb6e4ee_add_economic_parameter_proposal_table.py` (new)
  - Create `economic_parameter_proposal` table with `if_not_exists` guards.

### B2: Provider reinvestment loop (P1) — ✅ complete

- File: `apps/miner/miner_app/reinvestment.py` (new)
  - `ReinvestmentEngine`, `ReinvestmentPolicy`, and `build_revenue_route`.
  - Uses `aitbc.agent_economics.Budget`, `OnChainAction`, and `RevenueRoute`.
- File: `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace.py`
  - `POST /marketplace/providers/{provider_id}/capacity` to publish updated capacity.
- File: `apps/coordinator-api/src/coordinator_api/contexts/marketplace/services/marketplace.py`
  - `MarketplaceService.update_provider_capacity` updates the provider's latest offer.

### B3: CLI extensions (P1) — ✅ complete

- File: `cli/aitbc_cli/commands/agent_wallet.py` (new)
  - `agent-wallet balance`, `agent-wallet stake`, `agent-wallet rebalance`.
- File: `cli/aitbc_cli/commands/economics.py`
  - `economics propose`, `economics vote`, `economics status` added to existing group.
- File: `cli/aitbc_cli/core/main.py`
  - Registers the `agent-wallet` command group.

### B4: Economic eventing & audit (P2) — ✅ complete

- File: `apps/coordinator-api/src/coordinator_api/contexts/analytics/economic_events.py` (new)
  - `EconomicEvent`, `EconomicEventType`, and in-memory `EventStore`.
- File: `scripts/audit/reconcile_agent_wallets.py` (new)
  - Reconciliation helper for agent wallet budgets and expected balances.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Coordination Protocol

- Agent A owns `aitbc/agent_economics/` and `aitbc/wallet/` shared types.
- Agent B owns `apps/coordinator-api` governance/economic domains and the CLI.
- Shared boundary: `aitbc/agent_economics/pricing.py` is consumed by the
  `apps/coordinator-api` marketplace; Agent A writes the pricing primitives
  first, then Agent B wires them.
- Sequence: Agent A lands wallet/escrow/bond/rebalance types before Agent B
  begins DAO governance and reinvestment service implementation.

## Release Gate

- [x] Agent wallet and escrow primitives are defined and tested.
- [x] Performance bond and staking models compile and have unit coverage.
- [x] Reinvestment policy and `Rebalancer` planner have unit tests.
- [x] Automated rebalancing loop passes simulation tests.
- [x] Dynamic fee market extends the existing Dynamic Pricing API.
- [x] OpenClaw DAO governance proposals for economic parameters are testable.
- [x] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
