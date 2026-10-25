# Node Mesh Management

**Level**: Intermediate
**Prerequisites**: Scenario 05 Island Creation, Scenario 21 Service Startup & Connectivity
**Estimated Time**: 20 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Node Mesh Management

---

## See Also

- **Previous Scenario**: [Edge Compute & Islands](./60_edge_compute_islands.md)
- **Next Scenario**: [Inter-Chain Trading](./62_interchain_trade.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/node/`

---

## Scenario Overview

> **Live vs. simulated:** `aitbc node` reads the local multichain config and
> queries each configured node's RPC — output is live where a node answers,
> and the CLI prints per-node errors where it does not. `node add`/`remove`
> edit the local node registry config only.

This scenario covers the `aitbc node` group beyond the island lifecycle
already played in scenario 05: the local node registry (`add`, `list`,
`remove`, `info`, `node-info`), connectivity checks (`monitor`, `test`),
cross-node chain inventory (`chains`, `node chain *`), island health, and
inter-island bridge requests.

### Use Case

An operator keeps a registry of fleet nodes, checks reachability and health,
lists the chains each node hosts, and reviews inter-island bridge requests.

### What You'll Learn

- The local node registry (`node add`, `node list`, `node info`/`node-info`, `node remove`)
- Health probing (`node test`, `node monitor`)
- Chain inventory (`node chains`, `node chain list-chains`)
- Island health from the node's own RPC (`node island list`, `node island health`)
- Bridge request review (`node bridge list-bridges`) and the gated
  approve/reject/request path

---

## Prerequisites

- `aitbc` configured with at least one node endpoint (scenario 03/05)
- A reachable blockchain RPC (`8202`) for `info`, `chains`, and island queries

---

## Steps

### 1. Inspect the local registry

```bash
aitbc node list
aitbc node list --format json
aitbc node info      --node-id node-1
aitbc node node-info --node-id node-1    # alias path of the same detail view
```

### 2. Probe a node

```bash
aitbc node test    --node-id node-1
aitbc node monitor --node-id node-1                # one-shot view
aitbc node monitor --node-id node-1 --realtime --interval 5   # streaming view
```

**Expected output:** connectivity status plus node metrics (uptime, CPU,
hosted chains) for `monitor`.

### 3. Chain inventory

```bash
aitbc node chains                     # chains across all configured nodes
aitbc node chains --node-id node-1
aitbc node chains --show-private      # include private-visibility chains
aitbc node chain list-chains          # active instances on this node
```

**Not played (starts/stops services — needs the operator's line):**

```bash
aitbc node chain start --chain-id side-1 --chain-type micro
aitbc node chain stop  --chain-id side-1
```

Starting or stopping a parallel chain instance changes the node's running
set; do not run on a validator node mid-era.

### 4. Island health

```bash
aitbc node island list                 # islands on this node's RPC
aitbc node island health               # health of each island
aitbc node island health --all         # include the default island
```

`node island create/join/leave/island-info/list-islands` are played in
scenario 05.

### 5. Bridge requests

```bash
aitbc node bridge list-bridges
```

**Not played (mutates bridge state — needs the operator's line):**

```bash
aitbc node bridge request --target-island-id <island-id>
aitbc node bridge approve --request-id req-123 --approving-node-id node-1
aitbc node bridge reject  --request-id req-123 --reason 'not authorized'
```

### 6. Registry edits (local config writes)

`node add`/`node remove` only edit the local multichain config — they do not
touch the remote node. Still, removing a registry entry other operators rely
on is a config change:

```bash
aitbc node add    --node-id node-1 --endpoint http://localhost:8202
aitbc node remove --node-id node-1 --force   # not played on shared config
```

---

## Cost Table

| Step | Spend |
|---|---|
| All registry, probe, and inventory steps | 0 AIT |

---

## Verification

- `aitbc node list` reflects any `add`/`remove`.
- `aitbc node test --node-id <id>` returns success for each registry entry.

## Troubleshooting

- `Error getting chains from node <id>` — that node's RPC is unreachable;
  the CLI continues with the remaining registry entries.
