# Pool Hub SLA End-to-End

**Level**: Intermediate
**Prerequisites**: [Scenario 13 Mining Setup](./13_mining_setup.md), [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-22
**Version**: 1.2

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

The pool hub runs on the **hub** node (port 8210) and maintains a **hub-wide
miner registry**. Shop/follower miners register and send heartbeats to the hub
over the public network (`HUB_POOL_HUB_URL`). `aitbc pool-hub status` reports
how many miners are online in that registry, regardless of which node you run
the CLI from.

On the hub, the CLI defaults to `http://localhost:8210`. On a shop/follower
node, the CLI resolves the hub from `HUB_DISCOVERY_URL` / `HUB_P2P_HOST` /
`HUB_RPC_URL` and reaches `http://<hub>/pool-hub`.

### Use Case

A shop operator confirms that the local miner is visible to the hub pool hub and
that SLA/billing data can be collected.

### What You'll Learn

- How to query pool-hub from the hub and from a shop/follower node
- Why `miners_online` should be at least 1 when `aitbc-miner` is running and
  registered
- How the canonical CLI resolves the pool hub URL without hard-coding the hub

---

## Prerequisites

### Tools Required

- `aitbc` on hub and shop

### Setup Required

On the hub (`hub.aitbc`):

- `aitbc-pool-hub.service` enabled and running
- `/etc/aitbc/aitbc-pool-hub.env` with Postgres/Redis/shared secret
- Nginx exposes `/pool-hub` to the public hostname

On the shop (`aitbc3`):

- `aitbc-miner.service` running
- `/etc/aitbc/blockchain.env` has `HUB_POOL_HUB_URL=http://hub.aitbc.bubuit.net/pool-hub`

---

## Step-by-Step Workflow

### Step 1: Hub-side CLI

On `hub.aitbc`:

```bash
aitbc pool-hub status
```

**Expected output:**

```json
{"status": "ok", "db": true, "redis": true, "miners_online": 1}
```

The `miners_online` count is `1` (or more) when at least one shop miner has
successfully registered with the hub pool hub.

```bash
aitbc pool-hub sla
```

**Expected output:**

```json
{"status": "healthy", "active_violations": 0, "recent_metrics_count": 0, "timestamp": "..."}
```

### Step 2: Shop-side or remote CLI

From the shop, the CLI discovers the hub pool hub automatically:

```bash
aitbc pool-hub status
```

**Expected output:** the same JSON with `miners_online: 1`.

To bypass discovery and hit a specific URL:

```bash
aitbc pool-hub status --pool-hub-url http://hub.aitbc.bubuit.net/pool-hub
```

### Step 3: Optional — start a miner

If the miner is not running:

```bash
aitbc mining start --wallet <miner-wallet>
aitbc mining status
aitbc pool-hub status
```

**Expected output:** mining status live on the shop. `miners_online` becomes at
least 1 as soon as the production miner registers with the hub pool hub.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run `aitbc pool-hub status` and `sla` from the hub and from a shop node and see `miners_online: 1`
- Query a remote pool hub with `--pool-hub-url`
- Start mining from `aitbc mining start` and verify hub-wide pool-hub visibility

---

## Validation

```bash
# On hub.aitbc
aitbc pool-hub status
aitbc pool-hub sla

# On aitbc3
aitbc pool-hub status
```

All three commands should return `status: ok` and `miners_online` > 0 when a
shop miner is online.

---

## Related Resources

- [Mining Setup](./13_mining_setup.md)
- [Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)

---

*Last updated: 2026-08-22*
*Version: 1.2*
