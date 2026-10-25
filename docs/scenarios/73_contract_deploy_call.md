# Contract Deploy & Call

**Level**: Intermediate
**Prerequisites**: Scenario 02 Transaction Sending, Scenario 56 Energy Pricing (EVM contract reads)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Contract Deploy & Call

---

## See Also

- **Previous Scenario**: [Developer Registry](./72_developer_registry.md)
- **Next Scenario**: [Confidential Payments](./74_confidential_payments.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/contract.py`

---

## Scenario Overview

> **Writes on-chain:** `contract deploy` submits a real deployment
> transaction (gas + a new contract address); `contract call` invokes a
> contract method — safe only for view/pure methods, state-changing calls
> spend gas and mutate storage. Both go through the blockchain RPC
> (`--rpc-url`, default `http://localhost:8202`).

This scenario covers the generic `aitbc contract` escape hatch for
deploying and calling EVM contracts by name/address.

### Use Case

An operator deploys a helper contract on an island chain or pokes a view
method on an already-deployed contract during debugging, without writing a
bespoke script.

### What You'll Learn

- `contract deploy` — deploy a named contract through the node RPC
- `contract call` — invoke a method with a JSON args array

---

## Prerequisites

- A reachable blockchain RPC (`8202`)
- For `deploy`: a funded deployer account configured for the CLI and a
  contract known to the deploy path
- For `call`: the contract address and its method ABI

---

## Steps

### 1. Read-only call

```bash
aitbc contract call --contract-address 0x<contract> --method 'balanceOf' \
    --args '["0x<account>"]'
```

`--args` is a JSON array. Only play `call` against view/pure methods —
a state-changing method sends a real transaction.

### 2. Deploy (write — not played without the operator's line)

```bash
aitbc contract deploy --contract-name MyContract --rpc-url http://localhost:8202
```

Deploys a real contract: spends gas, creates a permanent address. Needs
the operator's line on a live island.

---

## Cost Table

| Step | Spend |
|---|---|
| `contract call` (view/pure method) | 0 AIT |
| `contract call` (state-changing method) | gas — not played |
| `contract deploy` | deployment gas — not played |

---

## Verification

- `call` returns the method's return value as decoded output.
- After `deploy` (when played), the new address answers `call` on a view
  method.

## Troubleshooting

- Method reverts / decode errors — check the ABI and the `--args` JSON
  array ordering.
- `RPC unreachable` — wrong `--rpc-url` or node stopped.
