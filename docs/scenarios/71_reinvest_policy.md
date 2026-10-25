# Reinvest Policy and Simulation

**Level**: Intermediate
**Prerequisites**: Scenario 13 Mining Setup, Scenario 40/49 (retired auto-reinvestment scenarios, archived)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Reinvest Policy

---

## See Also

- **Previous Scenario**: [Script Runner](./70_script_runner.md)
- **Next Scenario**: [Developer Registry](./72_developer_registry.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/reinvest.py`; retired
  plays `docs/archive/scenarios/40_auto_reinvestment.md`,
  `49_auto_reinvest_escrow.md`

---

## Scenario Overview

> **Local computation:** `aitbc reinvest` runs the miner's reinvestment
> logic locally (it imports the miner app) — `policy` shows/sets the split
> and `simulate` projects an earnings split without touching the chain.
> No funds move.

This scenario covers `aitbc reinvest`: the staking/reserve policy for
miner earnings and a dry-run split simulation.

### Use Case

A GPU provider wants a fixed share of released-escrow earnings restaked
automatically. Before enabling it they simulate the split over a typical
earning amount and check the reserve floor.

### What You'll Learn

- `reinvest policy` — the agent's staking/reserve/min-reinvest policy
- `reinvest simulate` — projected split for a given earnings amount

---

## Prerequisites

- `aitbc` on `$PATH` with the miner package available (the command loads
  the miner app; on a non-miner node it may fail to import — run on a GPU
  node)
- An agent id to scope the policy to

---

## Steps

### 1. Show or set the policy

```bash
aitbc reinvest policy --agent-id agent-1 \
    --staking-pct 0.30 --reserve-pct 0.10 --min-reinvest 1.0
```

**Expected output:** the resulting policy — share of earnings restaked,
share held in reserve, and the minimum earning that triggers a reinvest.
Setting the policy is a local/agent config write, not a chain transaction.

### 2. Simulate a split

```bash
aitbc reinvest simulate --agent-id agent-1 --earnings 100 \
    --budget-total 500 --staking-contract 0x<staking> --reserve-address 0x<reserve>
```

**Expected output:** how `earnings` would split between the staking
contract, the reserve address, and spendable balance under the current
policy — labelled a simulation; no funds move.

---

## Cost Table

| Step | Spend |
|---|---|
| Entire scenario | 0 AIT — local policy math only |

---

## Verification

- Re-running `simulate` with the same inputs gives the same split.
- The projected staking amount equals `earnings × staking_pct` (within
  rounding).

## Troubleshooting

- Import error on a non-miner node — the command needs the miner app;
  run it on the GPU node (node2 in the reference fleet).
