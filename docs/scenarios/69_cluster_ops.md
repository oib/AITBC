# Cluster Ops

**Level**: Beginner
**Prerequisites**: Scenario 61 Node Mesh Management
**Estimated Time**: 5 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Cluster Ops

---

## See Also

- **Previous Scenario**: [RPC Performance](./68_rpc_performance.md)
- **Next Scenario**: [Script Runner](./70_script_runner.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/cluster.py`

---

## Scenario Overview

> **Stub output:** the three `aitbc cluster` leaves currently return a
> built-in local result — `status` reports a fixed health map and
> `sync`/`balance` report a completed action — they do **not** query a live
> cluster service. Treat the output as a CLI stub until a real cluster
> backend lands; do not read fleet state into it.

This scenario covers `aitbc cluster status`, `cluster sync`, and
`cluster balance`.

### Use Case

Placeholder surface for multi-node cluster health, re-sync, and shard
rebalancing. The play documents what the CLI prints today so operators are
not misled by the stub values.

### What You'll Learn

- The three cluster leaves and their (stub) output shape
- Why `cluster status` does not reflect the real fleet

---

## Prerequisites

- `aitbc` on `$PATH`; no service required (commands cannot fail on network)

---

## Steps

### 1. Status, sync, balance

```bash
aitbc cluster status
aitbc cluster status --output json
aitbc cluster sync
aitbc cluster balance
```

**Expected output (stub):**

```
Cluster Status
  cluster_health: healthy
  nodes: 3
  active_nodes: 3

Cluster Sync
  action: cluster_sync
  status: completed

Cluster Balance
  action: cluster_balance
  status: completed
```

The `nodes: 3` figure is hardcoded in the CLI — it is not a count of the
live fleet. For real node state use `aitbc node list` / `aitbc node
chains` (scenario 61).

---

## Cost Table

| Step | Spend |
|---|---|
| Entire scenario | 0 AIT |

---

## Verification

- Output shape matches the stub table above; any divergence means the
  backend landed and this scenario needs updating.

## Troubleshooting

- None — these commands do not reach the network.
