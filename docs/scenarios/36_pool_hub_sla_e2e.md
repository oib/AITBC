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

The pool hub runs on the hub (8210, nginx `/pool-hub/`). Shop/follower CLIs resolve it via `HUB_DISCOVERY_URL` / `HUB_P2P_HOST` and run `aitbc pool-hub status` / `sla`. `miners_online` stays 0 until a miner registers with the **hub** pool — the shop miner currently heartbeats the **local** coordinator.

### Use Case

A shop operator confirms SLA metrics from the follower without hardcoding a hub URL.

### What You'll Learn

- How to query pool-hub from hub and shop with the same CLI
- Why `miners_online` can be 0 on a healthy shop miner
- How to start mining from the CLI as an optional follow-up

---

## Prerequisites

### Tools Required

- `aitbc` on hub and shop

### Setup Required

On the hub:

- `aitbc-pool-hub.service` enabled
- `/etc/aitbc/aitbc-pool-hub.env` with Postgres/Redis/shared secret
- nginx `location /pool-hub/`

On the shop:

- `HUB_DISCOVERY_URL` or `HUB_P2P_HOST` / `HUB_RPC_URL` in `/etc/aitbc/{blockchain,node}.env`

---

## Step-by-Step Workflow

### Step 1: Hub-side CLI

On the hub:

```bash
aitbc pool-hub status
aitbc pool-hub sla
```

**Expected output:**

```json
{"status": "ok", "db": true, "redis": true, "miners_online": 0}
```

```json
{"status": "healthy", "active_violations": 0, "recent_metrics_count": 0, "timestamp": "..."}
```

### Step 2: Shop/follower CLI (same commands)

On `aitbc3`:

```bash
aitbc pool-hub status
aitbc pool-hub sla
```

**Expected output:** the same JSON. The CLI must not talk to localhost:8210 on the shop.

### Step 3: Optional — start a miner

```bash
aitbc mining start --wallet <miner-wallet>
aitbc mining status
aitbc pool-hub status
```

**Expected output:** mining status live on the shop. `miners_online` becomes 1 **only if** that miner registers with the hub pool. Today it often stays 0; that is a product gap (DESIGN_CYCLE P0.2), not a CLI failure.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run `aitbc pool-hub status` and `sla` from hub and shop
- Interpret `miners_online: 0` correctly
- Start mining from `aitbc mining start`

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
