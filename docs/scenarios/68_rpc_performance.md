# RPC Performance

**Level**: Beginner
**Prerequisites**: Scenario 15 Blockchain Monitoring
**Estimated Time**: 10 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > RPC Performance

---

## See Also

- **Previous Scenario**: [DAO Grants](./67_dao_grants.md)
- **Next Scenario**: [Cluster Ops](./69_cluster_ops.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/performance.py`

---

## Scenario Overview

> **Live vs. simulated:** `performance benchmark` samples the **real**
> blockchain RPC — `/rpc/head`, `/rpc/network-info`, `/rpc/mempool` — and
> reports measured latency, not fabricated numbers. `optimize` and `tune`
> are a documented CLI gap: the node has no performance endpoints, so both
> abort with a "not implemented" message by design.

This scenario covers `aitbc performance`: a real RPC latency/health
benchmark plus the two unimplemented tuner leaves.

### Use Case

Before blaming the network for slow jobs, an operator measures actual RPC
read latency and current chain stats on the node under test.

### What You'll Learn

- `performance benchmark` — measured RPC read latency and live chain stats
- The `optimize`/`tune` CLI gap (expected failure, no server endpoints)

---

## Prerequisites

- A reachable blockchain RPC (`--rpc-url`, default `http://localhost:8202`)

---

## Steps

### 1. Benchmark the RPC

```bash
aitbc performance benchmark
aitbc performance benchmark --rpc-url http://localhost:8202
```

**Expected output:** min/avg/max read latency in ms plus live `chain_height`,
`peer_count`, and `mempool_pending`. Fails with `RPC unreachable at …` when
the node is down — that failure *is* the result on a dead node.

### 2. Tuner leaves (expected CLI gap)

```bash
aitbc performance optimize
aitbc performance tune
```

**Expected output:** both abort with `Not implemented: the blockchain node
has no performance-optimization/-tuning endpoint`. Documented here for
coverage; do not script against them until a server endpoint exists.

---

## Cost Table

| Step | Spend |
|---|---|
| Entire scenario | 0 AIT — read-only RPC samples |

---

## Verification

- `latency_ms_avg` is plausible (< 100 ms on a LAN node); `chain_height`
  matches `aitbc blockchain height`.
- `optimize`/`tune` fail with the not-implemented message, not a traceback.

## Troubleshooting

- `RPC unreachable` — wrong `--rpc-url` or the blockchain node is stopped.
