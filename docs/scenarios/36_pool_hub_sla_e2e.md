# Pool Hub SLA End-to-End

**Level**: Intermediate
**Prerequisites**: [Scenario 13 Mining Setup](./13_mining_setup.md), [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-21
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Pool Hub SLA End-to-End

---

## See Also

- **Previous Scenario**: [Scenario 35 Fire-and-Forget Logging (B10/B11)](./35_fire_and_forget_logging_b10_b11.md)
- **Feature Documentation**: [Service Ports Reference](../reference/SERVICE_PORTS.md)
- **Closed cycle**: [DESIGN_CYCLE.md](../DESIGN_CYCLE.md) (P0.2: hub-visible miners)

---

## Scenario Overview

The pool hub runs on the **shop** node (port 8210). The `aitbc-miner` service registers with the local pool hub and sends heartbeats. `aitbc pool-hub status` reports how many miners are online in that pool hub. On the shop the CLI defaults to `http://localhost:8210`; from the hub or another node you can pass `--pool-hub-url http://aitbc3:8210` or set `POOL_HUB_URL`.

### Use Case

A shop operator confirms that the local miner is visible to the pool hub and that SLA/billing data can be collected.

### What You'll Learn

- How to query pool-hub from the shop and from a remote node
- Why `miners_online` on the shop should be at least 1 when `aitbc-miner` is running
- How to start mining from the CLI as an optional follow-up

---

## Prerequisites

### Tools Required

- `aitbc` on hub and shop

### Setup Required

On the shop (e.g. `aitbc3`):

- `aitbc-pool-hub.service` enabled and running
- `/etc/aitbc/aitbc-pool-hub.env` with Postgres/Redis/shared secret
- `aitbc-miner.service` running and registered with the local pool hub

On the hub or a follower:

- `aitbc` CLI installed
- (optional) `HUB_POOL_HUB_URL` or `POOL_HUB_URL` env var to reach the shop pool hub

---

## Step-by-Step Workflow

### Step 1: Shop-side CLI

On `aitbc3`:

```bash
aitbc pool-hub status
```

**Expected output:**

```json
{"status": "ok", "db": true, "redis": true, "miners_online": 1}
```

The `miners_online` count is `1` (or more) when `aitbc-miner` has successfully registered with the local pool hub.

```bash
aitbc pool-hub sla
```

**Expected output:**

```json
{"status": "healthy", "active_violations": 0, "recent_metrics_count": 0, "timestamp": "..."}
```

### Step 2: Hub-side or remote CLI

From the hub, point at the shop pool hub:

```bash
aitbc pool-hub status --pool-hub-url http://aitbc3:8210
```

**Expected output:** the same JSON with `miners_online: 1` if the shop miner is online.

### Step 3: Optional — start a miner

If the miner is not running:

```bash
aitbc mining start --wallet <miner-wallet>
aitbc mining status
aitbc pool-hub status
```

**Expected output:** mining status live on the shop. `miners_online` becomes 1 as soon as the production miner registers with the pool hub.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run `aitbc pool-hub status` and `sla` from the shop and see `miners_online: 1`
- Query a remote pool hub with `--pool-hub-url`
- Start mining from `aitbc mining start` and verify pool-hub visibility

---

## Validation

```bash
# Optional HTTP health through nginx — not the play
# curl -s --max-time 5 https://hub.aitbc.bubuit.net/pool-hub/health
aitbc pool-hub status
aitbc pool-hub sla
```

---

## Related Resources

- [Mining Setup](./13_mining_setup.md)
- [Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)

---

*Last updated: 2026-08-21*
*Version: 1.1*
