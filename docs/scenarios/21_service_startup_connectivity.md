# Service Startup & Connectivity

**Level**: Intermediate
**Prerequisites**: [Scenario 20 Cross-Chain Transfer](./20_cross_chain_transfer.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-07-05
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Service Startup & Connectivity

---

## See Also

- **Previous Scenario**: [Scenario 20 Cross-Chain Transfer](./20_cross_chain_transfer.md)
- **Next Scenario**: [Scenario 22 Bridge RPC Input Validation](./22_bridge_rpc_validation.md)
- **Feature Documentation**: [Service Ports Reference](../reference/SERVICE_PORTS.md)

---

## Scenario Overview

This scenario verifies that all shop-node services start correctly and connect to their upstream dependencies using the right ports. It covers the A3 fix (default port corrections: miner coordinator URL 8011->8107, edge agent-coordinator URL 8010->8107) and the B9 fix (edge registration errors are logged, not silently swallowed).

### Use Case

A node operator restarts a shop node after an upgrade and needs to confirm that the miner is sending heartbeats to the coordinator API, the edge service registered on the blockchain, and all health endpoints respond.

### What You'll Learn

- How to verify service startup via `systemctl` and `journalctl`
- How to check that the miner connects to the coordinator API on port 8203
- How to confirm the edge service registers on the blockchain via the bridge RPC
- How to verify health endpoints for edge (`8111`) and bridge (`8202`)

---

## Prerequisites

### Knowledge Required

- Basic familiarity with systemd service management
- Understanding of the AITBC service architecture (miner, edge, blockchain-node, coordinator-api)

### Tools Required

- `systemctl`, `journalctl` (system service management)
- `curl` (HTTP requests)

### Setup Required

- A running AITBC shop node with all services deployed
- Services: `aitbc-miner`, `aitbc-edge`, `aitbc-blockchain-rpc`, `aitbc-coordinator-api`, `aitbc-blockchain-node`

---

## Step-by-Step Workflow

### Step 1: Check All Services Are Running

```bash
systemctl is-active aitbc-miner aitbc-edge aitbc-blockchain-rpc aitbc-coordinator-api aitbc-blockchain-node
```

**Expected output:**

```
active
active
active
active
active
```

### Step 2: Verify Miner Heartbeats (A3)

The miner should send heartbeats to the coordinator API. Check the env override and the logs:

```bash
# Check the coordinator URL the miner uses
systemctl cat aitbc-miner | grep COORDINATOR_URL

# Check recent heartbeat logs
journalctl -u aitbc-miner -n 10 --no-pager | grep "Heartbeat sent"
```

**Expected output:**

```
Environment="COORDINATOR_URL=http://localhost:8203"
Jul 05 14:27:26 aitbc3 aitbc-miner[999]: [INFO] [production_miner] Heartbeat sent (GPU: 19%)
Jul 05 14:27:42 aitbc3 aitbc-miner[999]: [INFO] [production_miner] Heartbeat sent (GPU: 41%)
```

### Step 3: Verify Edge Registration on Blockchain (B9)

The edge service should register itself on the blockchain on startup. If registration fails, the error must be logged (not silently swallowed):

```bash
# Restart edge to trigger registration
systemctl restart aitbc-edge
sleep 3

# Check registration log
journalctl -u aitbc-edge --since "10 sec ago" --no-pager | grep -E "register|blockchain"
```

**Expected output:**

```
Jul 05 14:28:13 aitbc3 python[50134]: [INFO] [httpx] HTTP Request: POST http://localhost:8202/rpc/edge/register "HTTP/1.1 200 OK"
Jul 05 14:28:13 aitbc3 python[50134]: [INFO] [aitbc_edge.main] Edge node registered on blockchain: edge-aitbc3
```

If the blockchain RPC is unavailable, you should see a WARNING (not a silent failure):

```
Jul 05 11:37:28 aitbc3 python[2207]: [WARNING] [aitbc_edge.main] Failed to register edge node on blockchain: All connection attempts failed
```

### Step 4: Verify Health Endpoints

```bash
# Edge health
curl -s http://localhost:8111/health

# Bridge health
curl -s http://localhost:8202/rpc/bridge/health
```

**Expected output:**

```json
{"status":"healthy","service":"edge-api","version":"0.1.0"}

{"success":true,"status":"healthy","bridge_initialized":true,"pending_transfer_count":0,...}
```

---

## Code Examples

### Verifying the Edge Config Default (A3)

The edge config default for `agent_coordinator_url` was corrected from `8010` to `8107`:

```python
# apps/edge/src/aitbc_edge/config.py
class EdgeSettings(BaseSettings):
    agent_coordinator_url: str = "http://localhost:8107"  # was 8010 before A3
```

### Verifying the Miner Config Default (A3)

The miner config default for `COORDINATOR_URL` was corrected from `8011` to `8107`:

```python
# apps/miner/production_miner.py
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://127.0.0.1:8107")  # was 8011 before A3
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm all shop-node services start and report active status
- Verify the miner sends heartbeats to the correct coordinator URL
- Confirm the edge service registers on the blockchain (or logs a warning on failure)
- Check health endpoints for edge and bridge services

---

## Validation

```bash
# All services active
systemctl is-active aitbc-miner aitbc-edge aitbc-blockchain-rpc aitbc-coordinator-api

# Miner heartbeats flowing
journalctl -u aitbc-miner -n 5 --no-pager | grep "Heartbeat sent"

# Edge registered
journalctl -u aitbc-edge -n 20 --no-pager | grep "registered on blockchain"

# Health endpoints
curl -sf http://localhost:8111/health && echo " edge OK"
curl -sf http://localhost:8202/rpc/bridge/health && echo " bridge OK"
```

---

## Related Resources

- [Service Ports Reference](../reference/SERVICE_PORTS.md)
- [Next Scenario: Bridge RPC Input Validation](./22_bridge_rpc_validation.md)

---

*Last updated: 2026-07-05*
*Version: 1.0*
