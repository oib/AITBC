# Simulated Workloads

**Level**: Beginner
**Prerequisites**: Scenario 23 Mempool Eviction Order (uses `simulate blockchain`)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Simulated Workloads

---

## See Also

- **Previous Scenario**: [Operations Admin](./64_operations_admin.md)
- **Next Scenario**: [Coordinator Workflows](./66_coordinator_workflows.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/simulate.py`

---

## Scenario Overview

> **Live vs. simulated:** every `aitbc simulate` leaf is **always
> simulated** — it generates deterministic local data and never touches the
> chain or a wallet. The `run`/`status`/`result` leaves are a known CLI
> gap: the agent-coordinator has no server-side `/simulate/*` endpoints, so
> they abort with a "not implemented" message by design.

This scenario covers the local simulators not already exercised by
scenarios 23/27 (`simulate blockchain`): wallets, price, network, and
ai-jobs — plus a documentation step for the unimplemented server-side trio.

### Use Case

An operator dry-runs fee pressure, price paths, network partitions, and AI
job mixes locally before tuning marketplace or consensus parameters —
with zero spend.

### What You'll Learn

- Local simulators: `simulate wallets`, `price`, `network`, `ai-jobs`
- Determinism via `--seed`
- The `simulate run`/`status`/`result` CLI gap (expected failure)

---

## Prerequisites

- `aitbc` on `$PATH`; no node, wallet, or service required

---

## Steps

### 1. Simulated wallets and transactions

```bash
aitbc simulate wallets --wallets 5 --balance 1000 --transactions 20 \
    --amount-range 1-50 --seed 42
```

**Expected output:** simulated wallet set with balances and a transaction
list — labelled simulated; `--seed` makes it reproducible.

### 2. Price path

```bash
aitbc simulate price --price 1.0 --volatility 0.05 --timesteps 50 --seed 42
```

### 3. Network simulation

```bash
aitbc simulate network --nodes 5 --network-delay 0.1 --failure-rate 0.05 --seed 42
```

Reports simulated message delivery, latency, and drop statistics.

### 4. AI job mix

```bash
aitbc simulate ai-jobs --jobs 10 --models 'llama3,whisper' --duration-range 5-60 \
    --delay 0 --seed 42
```

Prints per-job durations plus aggregate model-usage statistics.

### 5. Server-side simulation (expected CLI gap)

```bash
aitbc simulate run    --scenario price --params '{"timesteps":10}'
aitbc simulate status --simulation-id sim-123
aitbc simulate result --simulation-id sim-123
```

**Expected output:** all three abort with
`Server-side simulation is not implemented: no '/simulate/*' endpoints
exist on the agent-coordinator.` This is intentional — the working
simulators are the local subcommands above. Not played as a success path;
documented here so the leaf coverage is complete and the gap is visible.

---

## Cost Table

| Step | Spend |
|---|---|
| Entire scenario | 0 AIT — local simulation only |

---

## Verification

- Same `--seed` → identical output on a re-run.
- `simulate blockchain` (scenario 23/27) plus the four simulators here
  cover every working leaf.

## Troubleshooting

- None — these commands cannot fail on missing services; a failure is a
  CLI bug, not an ops issue.
