# Edge Compute, Islands, and Databases

**Level**: Intermediate
**Prerequisites**: Scenario 05 Island Creation, Scenario 21 Service Startup & Connectivity
**Estimated Time**: 25 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Edge Compute & Islands

---

## See Also

- **Previous Scenario**: [Sepolia Buy/Sell AIT](./59_sepolia_buy_sell_ait.md)
- **Next Scenario**: [Node Mesh Management](./61_node_mesh_management.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/edge.py`

---

## Scenario Overview

> **Live vs. simulated:** `aitbc edge` talks to the **local edge API**
> (`/v1/edge-gpu`, `/v1/gpu`, `/v1/serve`, `/v1/metrics`, `/v1/database`).
> When the edge service is not running on the node, every command fails with
> a network error — there is no simulated fallback. Run this play on a node
> that actually runs the edge service.

This scenario covers the `aitbc edge` surface end to end: wallet/balance
queries, GPU inventory and metrics, island membership and bridging, edge
databases, and the compute `serve` request lifecycle.

### Use Case

An edge operator checks the node's edge wallet, scans and inspects its
GPUs, joins/leaves islands, keeps edge-side databases in sync, and submits
small compute requests to a specific edge GPU.

### What You'll Learn

- Edge wallet state (`status`, `balance`, `transfer`)
- Edge GPU inventory and metrics (`gpu scan-gpus`, `gpu get-gpu`, `gpu gpu-metrics`, `metrics *`)
- Island membership from the edge side (`island join`, `island list`, `island get`, `island bridge`, `island leave`)
- Edge databases (`database init-db`, `list-dbs`, `get-db`, `sync-db`, `delete-db`)
- The compute request lifecycle (`serve submit-request`, `list-requests`, `get-request`, `get-result`, `cancel-request`)

---

## Prerequisites

- A node running the edge service (the edge API must be reachable; every
  subcommand errors out otherwise)
- Scenario 05 for the island model; scenario 21 for the connectivity checks

---

## Steps

### 1. Edge status and balance

```bash
aitbc edge status
aitbc edge balance
aitbc edge balance --output json
```

**Expected output:** the edge status map, then the edge wallet balance
(integer units; `UNITS_PER_AIT = 36_000_000`).

### 2. GPU inventory

```bash
aitbc edge gpu scan-gpus --miner-id <miner-id>   # refresh the edge-side GPU list
aitbc edge gpu list-gpus                          # covered by scenario 27
aitbc edge gpu get-gpu --gpu-id gpu-1
aitbc edge gpu gpu-metrics --gpu-id gpu-1 --limit 20
```

**Not played:** `aitbc edge gpu remove-gpu --gpu-id <id>` deregisters a GPU
from the edge inventory — destructive; needs the operator's line.

### 3. Record and inspect metrics

```bash
aitbc edge metrics record --gpu-id gpu-1 --metrics '{"temperature":60}'
aitbc edge metrics list-metrics --gpu-id gpu-1 --limit 50
aitbc edge metrics get-metric --metric-id <metric-id>
```

**Not played:** `aitbc edge metrics delete-metric --metric-id <id>` removes a
recorded sample — destructive; needs the operator's line before running on a
live node.

### 4. Island membership

```bash
aitbc edge island list
aitbc edge island get --island-id <island-id>
```

**Not played (writes membership state — need the operator's line):**

```bash
aitbc edge island join  --island-id <id> --island-name <name> --chain-id <chain> --role compute-provider --confirm
aitbc edge island leave --island-id <id>
aitbc edge island bridge --target-island-id <id>
```

Joining an island, leaving one, or requesting an edge-side bridge changes
the node's registered role; do not run these against the production island.

### 5. Edge databases

```bash
aitbc edge database init-db  --database-id db-1 --island-id <island-id> --capacity-gb 10
aitbc edge database list-dbs --island-id <island-id>
aitbc edge database get-db   --database-id db-1
aitbc edge database sync-db  --database-id db-1
```

**Not played:** `aitbc edge database delete-db --database-id db-1` drops the
edge database — destructive; needs the operator's line.

### 6. Compute requests (`serve`)

```bash
aitbc edge serve submit-request --gpu-id gpu-1 --model-name model-1 \
    --input-data '{"x":1}' --priority normal --job-id job-123
aitbc edge serve list-requests --gpu-id gpu-1 --status pending
aitbc edge serve get-request --request-id <request-id>
aitbc edge serve get-result  --request-id <request-id>
```

`--job-id` links the request to a paid marketplace job for edge servers that
verify escrow; omit it only on a test edge server. `--escrow-id` is the
legacy verification field.

**Not played:** `aitbc edge serve cancel-request --request-id <id>` aborts a
queued request — only cancel requests you own.

### 7. Edge transfer (spends — operator line required)

`aitbc edge transfer --to-address <addr> --amount <n>` (optional `--note <text>`) moves AIT out
of the edge wallet. Any amount is a real spend; not played without the
operator's line.

---

## Cost Table

| Step | Spend |
|---|---|
| 1–6 read-only queries and metric records | 0 AIT |
| `edge transfer` | `--amount` (integer units) — not played |

---

## Verification

- `aitbc edge balance` unchanged after all read-only steps.
- `aitbc edge gpu list-gpus` shows any newly scanned GPU.
- `aitbc edge database list-dbs` shows `db-1` after `init-db`.

## Troubleshooting

- `Network error: …` on every command — the edge service is not running on
  this node; `aitbc edge` has no simulated fallback.
