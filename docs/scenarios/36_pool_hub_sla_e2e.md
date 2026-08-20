# Pool Hub SLA End-to-End

**Level**: Intermediate
**Prerequisites**: [Scenario 13 Mining Setup](./13_mining_setup.md), [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-20
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Pool Hub SLA End-to-End

---

## See Also

- **Previous Scenario**: [Scenario 35 Fire-and-Forget Logging (B10/B11)](./35_fire_and_forget_logging_b10_b11.md)
- **Feature Documentation**: [Service Ports Reference](../reference/SERVICE_PORTS.md)
- **Pool Hub App**: [apps/pool-hub/README.md](../../../apps/pool-hub/README.md)

---

## Scenario Overview

This scenario verifies that the **pool hub** service runs on the hub node and is reachable from a follower/shop node. It exercises the `aitbc pool-hub` CLI group (`status` and `sla`) from both the hub and a follower, confirming that hub discovery, nginx routing, and PostgreSQL/Redis backends are wired correctly.

### Use Case

A shop/follower operator wants to confirm the hub is tracking miner health and SLA metrics before attaching a miner to a pool. They need `aitbc pool-hub status` and `aitbc pool-hub sla` to succeed from the shop without hardcoding a hub URL.

### What You Will Learn

- How to install and enable `aitbc-pool-hub.service` on the hub
- How to expose the pool hub through nginx at `/pool-hub/`
- How the follower CLI resolves the hub via `HUB_DISCOVERY_URL` / `HUB_P2P_HOST`
- How to validate the pool hub database and Redis backends from both nodes

---

## Prerequisites

### Knowledge Required

- Familiarity with systemd services and nginx reverse-proxy locations
- Understanding of the hub/follower node topology
- Basic `aitbc mining` commands

### Tools Required

- AITBC CLI (`aitbc`) installed on both hub and follower
- `systemctl` and `nginx` on the hub
- PostgreSQL and Redis on the hub

### Setup Required

On the **hub** (`hub.aitbc`):

- `aitbc-pool-hub.service` linked into `/etc/systemd/system/` and enabled
- `/etc/aitbc/aitbc-pool-hub.env` with valid `POOLHUB_POSTGRES_DSN`, `POOLHUB_REDIS_URL`, and `POOLHUB_COORDINATOR_SHARED_SECRET`
- nginx `upstream pool_hub { server 127.0.0.1:8210; }` and `location /pool-hub/` proxying to that upstream
- The `aitbc_poolhub` PostgreSQL database exists and is reachable

> **Note**: `apps/pool-hub/src/poolhub/settings.py` currently hardcodes `postgresql+asyncpg://poolhub:poolhub@127.0.0.1:5432/aitbc` for the `database.url` default. If the `aitbc` database does not exist, ensure the service uses the `POOLHUB_POSTGRES_DSN` from the environment before starting.

On the **follower** (`aitbc3`):

- `HUB_DISCOVERY_URL`, `HUB_P2P_HOST`, or `HUB_RPC_URL` in `/etc/aitbc/blockchain.env` or `/etc/aitbc/node.env` points at the hub
- `aitbc` CLI can resolve the hub

---

## Step-by-Step Workflow

### Step 1: Verify the Pool Hub Service on the Hub

On the **hub node**:

```bash
systemctl is-active aitbc-pool-hub
ss -ltnp | grep 8210
```

**Expected output:**

```text
active
LISTEN 0  2048  127.0.0.1:8210  ...
```

### Step 2: Query Pool Hub from the Hub

On the **hub node** (or via SSH to the hub):

```bash
aitbc pool-hub status
aitbc pool-hub sla
```

**Expected output:**

```json
{
  "status": "ok",
  "db": true,
  "redis": true,
  "miners_online": 0
}
```

```json
{
  "status": "healthy",
  "active_violations": 0,
  "recent_metrics_count": 0,
  "timestamp": "..."
}
```

> `miners_online` is `0` until a miner is started and registers with the hub.

### Step 3: Query Pool Hub from a Follower/Shop Node

On the **shop node** (`aitbc3`):

```bash
aitbc pool-hub status
aitbc pool-hub sla
```

**Expected output:**

Same JSON as in Step 2, because the CLI resolves `https://<hub>/pool-hub/` and the nginx route proxies to `http://127.0.0.1:8210` on the hub.

### Step 4: Optional — Start a Miner and Watch `miners_online`

On the **shop node** (`aitbc3`):

```bash
aitbc mining start --wallet <miner-wallet>
aitbc pool-hub status
```

**Expected output:**

After the miner registers, `miners_online` becomes `1`.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Install, enable, and expose `aitbc-pool-hub` on the hub
- Confirm the hub database and Redis are reachable
- Run `aitbc pool-hub status` and `aitbc pool-hub sla` from the hub
- Run the same commands from a follower node and get the same results
- Understand how `miners_online` reflects registered miners

---

## Validation

```bash
# On the hub: direct localhost check
curl -s http://127.0.0.1:8210/health

# On the follower: through the public nginx route
curl -s --max-time 5 https://hub.aitbc.bubuit.net/pool-hub/health

# CLI checks
aitbc pool-hub status
aitbc pool-hub sla
```

All calls should return JSON with `status: ok` or `status: healthy` and no connection errors.

---

## Related Resources

- [Service Ports Reference](../reference/SERVICE_PORTS.md)
- [Mining Setup](./13_mining_setup.md)
- [Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
- [apps/pool-hub/aitbc-pool-hub.service](../../../apps/pool-hub/aitbc-pool-hub.service)

---

*Last updated: 2026-08-20*
*Version: 1.0*
