# v0.12.0 — OpenClaw Autonomous Economics

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

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
  - `MarketMakerStrategy`, demand forecast, and surge pricing primitives.
  - Extend existing Dynamic Pricing API types.

---

## Agent B — Applications, DAO & CLI

### B1: OpenClaw DAO economic governance (P2)

- File: `apps/coordinator-api/src/coordinator_api/contexts/governance/domain/economic_proposal.py` (new)
  - SQLModel `EconomicParameterProposal`.
- File: `apps/coordinator-api/alembic/versions/` (new migration)
  - Create `economic_parameter_proposal` table.

### B2: Provider reinvestment loop (P1)

- File: `apps/miner/src/miner_app/reinvestment.py` (TBD)
  - Autonomous reinvestment of earned AITBC into GPU/storage capacity.
- File: `apps/coordinator-api/src/coordinator_api/contexts/marketplace/` (TBD)
  - APIs to publish updated provider capacity after reinvestment.

### B3: CLI extensions (P1)

- File: `cli/aitbc_cli/commands/agent_wallet.py` (new)
  - `agent-wallet balance`, `agent-wallet stake`, `agent-wallet rebalance`.
- File: `cli/aitbc_cli/commands/economics.py` (new)
  - `economics propose`, `economics vote`, `economics status`.

### B4: Economic eventing & audit (P2)

- File: `apps/coordinator-api/src/coordinator_api/contexts/analytics/economic_events.py` (new)
  - Event log for lease, payment, slash, and rebalance events.
- File: `scripts/audit/reconcile_agent_wallets.py` (new)
  - Reconciliation helper for agent wallets and escrow.

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
- [ ] Automated rebalancing loop passes simulation tests.
- [ ] Dynamic fee market extends the existing Dynamic Pricing API.
- [ ] OpenClaw DAO governance proposals for economic parameters are testable.
- [ ] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
