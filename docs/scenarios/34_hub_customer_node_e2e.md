# Hub↔Customer Node End-to-End

**Level**: Intermediate
**Prerequisites**: [Scenario 33 Exchange Financial Correctness](./33_exchange_financial_correctness.md)
**Estimated Time**: 25 minutes
**Last Updated**: 2026-08-19
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Hub↔Customer Node End-to-End

---

## See Also

- **Previous Scenario**: [Scenario 33 Exchange Financial Correctness](./33_exchange_financial_correctness.md)
- **Next Scenario**: [Scenario 35 Fire-and-Forget Logging (B10/B11)](./35_fire_and_forget_logging_b10_b11.md)
- **Feature Documentation**: [Service Ports Reference](../reference/SERVICE_PORTS.md)
- **Release Notes**: [v0.10.3 Change Log](../releases/v0.10.3/change.log)

---

## Scenario Overview

This scenario verifies that a **customer node** (a separate machine or separate CLI profile) can reach the **hub node** across the network and exercise the full product path: job submission, bridge operations, exchange trading, and agent coordination. It covers the **A6** fix (coordinator-api no longer hardcodes `localhost:8202` for blockchain RPC — it uses `settings.blockchain_rpc_url`), ensuring the hub's internal services work correctly when the blockchain node is reachable via a configured URL rather than a hardcoded localhost address.

### Use Case

A customer node operator on a separate machine wants to submit AI jobs to the hub's coordinator-api, trade on the hub's exchange, and bridge tokens cross-chain via the hub's blockchain-node RPC. The hub's coordinator-api must correctly route internal blockchain queries (settlement, governance) to the blockchain node using the configured URL, not a hardcoded `localhost:8202`.

### What You'll Learn

- How to configure the AITBC CLI on a customer node to point at a remote hub
- How to verify the hub's coordinator-api uses `settings.blockchain_rpc_url` (A6) instead of hardcoded `localhost`
- How to submit a job from the customer node to the hub's coordinator-api
- How to query the hub's bridge RPC from the customer node
- How to trade on the hub's exchange from the customer node
- How to verify end-to-end connectivity across the hub↔customer topology

---

## Prerequisites

### Knowledge Required

- Familiarity with the AITBC service architecture (hub vs customer node)
- Understanding of network-accessible service ports
- Basic familiarity with the AITBC CLI command groups

### Tools Required

- AITBC CLI (`aitbc`) installed on both hub and customer node
- `curl` (HTTP requests)
- `journalctl` (hub-side log inspection)

### Setup Required

- **Hub node**: all AITBC services running, network-accessible IP (e.g., `192.168.100.10` or `hub.aitbc.bubuit.net`)
- **Customer node**: AITBC CLI installed, network access to hub's ports (8202, 8203, 8106, 8107, 8108)
- Hub's blockchain RPC (8202), coordinator-api (8203), exchange (8106), agent-coordinator (8107) must be reachable from the customer node

---

## Step-by-Step Workflow

### Step 1: Identify the Hub's Network Address

On the **hub node**:

```bash
HUB_IP=$(hostname -I | awk '{print $1}')
HUB_HOST=$(hostname)
echo "Hub IP: $HUB_IP"
echo "Hub hostname: $HUB_HOST"
```

**Expected output:**

```
Hub IP: 192.168.100.10
Hub hostname: hub.aitbc.bubuit.net
```

### Step 2: Verify Hub Services Listen on Network-Accessible Interfaces

On the **hub node**:

```bash
# Check which interfaces the key services bind to
ss -ltnp | grep -E '8202|8203|8106|8107|8108'
```

**Expected output:**

```
LISTEN 0  256  127.0.0.1:8202  ...   # blockchain RPC (localhost only — see note)
LISTEN 0  256  127.0.0.1:8203  ...   # coordinator-api (localhost only — see note)
LISTEN 0  5    127.0.0.1:8106  ...   # exchange (localhost only — see note)
LISTEN 0  2048 127.0.0.1:8107  ...   # agent-coordinator (localhost only)
LISTEN 0  2048 0.0.0.0:8108    ...   # wallet (all interfaces)
```

> **⚠️ Note**: If services bind to `127.0.0.1` only, the customer node cannot reach them directly. You have two options:
>
> 1. **SSH tunnel** (recommended for testing): `ssh -L 8202:localhost:8202 -L 8203:localhost:8203 -L 8106:localhost:8106 -L 8107:localhost:8107 user@hub.aitbc.bubuit.net`
> 2. **Rebind services** to `0.0.0.0` (production: ensure firewall rules restrict access)

### Step 3: Configure the Customer Node CLI to Point at the Hub

On the **customer node**:

```bash
# Set environment variables to override CLI defaults
export BLOCKCHAIN_RPC_URL="http://hub.aitbc.bubuit.net:8202"
export AGENT_COORDINATOR_URL="http://hub.aitbc.bubuit.net:8107"
export EXCHANGE_SERVICE_URL="http://hub.aitbc.bubuit.net:8106/api/v1"
export WALLET_URL="http://hub.aitbc.bubuit.net:8108"

# Or write to /etc/aitbc/node.env on the customer node
cat > /etc/aitbc/node.env <<'EOF'
BLOCKCHAIN_RPC_URL=http://hub.aitbc.bubuit.net:8202
AGENT_COORDINATOR_URL=http://hub.aitbc.bubuit.net:8107
EXCHANGE_SERVICE_URL=http://hub.aitbc.bubuit.net:8106/api/v1
WALLET_URL=http://hub.aitbc.bubuit.net:8108
EOF

# Verify the CLI picks up the overrides
aitbc config show 2>/dev/null || python3 -c "
from cli.aitbc_cli.config import get_config
c = get_config()
print(f'blockchain_rpc_url: {c.blockchain_rpc_url}')
print(f'agent_coordinator_url: {c.agent_coordinator_url}')
print(f'exchange_service_url: {c.exchange_service_url}')
print(f'wallet_url: {c.wallet_url}')
"
```

**Expected output:**

```
blockchain_rpc_url: http://hub.aitbc.bubuit.net:8202
agent_coordinator_url: http://hub.aitbc.bubuit.net:8107
exchange_service_url: http://hub.aitbc.bubuit.net:8106/api/v1
wallet_url: http://hub.aitbc.bubuit.net:8108
```

### Step 4: Verify Cross-Network Connectivity

On the **customer node**:

```bash
# Test each hub service endpoint
for port in 8202 8203 8106 8107 8108; do
  printf "Port %s: " "$port"
  curl -s --max-time 5 "http://hub.aitbc.bubuit.net:$port/health" 2>/dev/null | head -c 80
  echo
done
```

**Expected output:**

```
Port 8202: {"success":true,"status":"healthy","bridge_initialized":true,...
Port 8203: {"status":"ok","env":"development","python_version":"3.13.5"}
Port 8106: {"status": "ok", "timestamp": "2026-07-05T..."}
Port 8107: {"status":"ok"}  (or similar)
Port 8108: {"status":"ok"}  (or similar)
```

> If any port returns `Connection refused`, the hub service is bound to `127.0.0.1` only — use the SSH tunnel from Step 2.

### Step 5: Verify A6 — Hub's Coordinator-API Uses Configured RPC URL

The A6 fix ensures the hub's coordinator-api uses `settings.blockchain_rpc_url` instead of hardcoded `localhost:8202` for settlement and governance queries. Verify the fix is in the deployed code:

On the **hub node**:

```bash
# Settlement hooks should use settings.blockchain_rpc_url (A6 fix)
grep "blockchain_rpc_url" /opt/aitbc/apps/coordinator-api/src/app/settlement/hooks.py

# Governance service should use env var with localhost fallback
grep "BLOCKCHAIN_RPC_URL\|blockchain_rpc_url" /opt/aitbc/apps/coordinator-api/src/app/contexts/governance/services/governance_service.py
```

**Expected output:**

```
response = httpx.get(f"{settings.blockchain_rpc_url}/rpc/chain")
blockchain_rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
```

**Interpretation:**

- `settlement/hooks.py` uses `settings.blockchain_rpc_url` (A6 fixed ✅)
- `governance_service.py` uses `os.getenv("BLOCKCHAIN_RPC_URL", ...)` (A6 fixed ✅ — no hardcoded localhost)

> **Before A6**: Both files had `url = "http://localhost:8202"` hardcoded, which would break if the blockchain node ran on a different host.

### Step 6: Submit a Job from the Customer Node to the Hub

On the **customer node** (or via SSH tunnel):

```bash
# Generate a JWT token on the hub (or use a customer-node token if auth is federated)
# For testing, generate on the hub and copy the token:
HUB_TOKEN=$(ssh hub.aitbc.bubuit.net 'cd /opt/aitbc && JWT_SECRET=$(grep JWT_SECRET /etc/aitbc/aitbc-coordinator-api.env | cut -d= -f2) PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
from coordinator_api.auth.jwt_auth import create_access_token
print(create_access_token(\"customer-node-user\", \"client\", {\"wallet_address\": \"0xCustomer1\"}))
"')

# Submit a job to the hub's coordinator-api
curl -s -w "\nHTTP %{http_code}" -X POST http://hub.aitbc.bubuit.net:8203/v1/jobs \
  -H "Authorization: Bearer $HUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"cross-node-test","image":"hello"}}'
```

**Expected output:**

```json
{"job_id":"...","state":"QUEUED","assigned_miner_id":null,"payment_status":"none"}
HTTP 201
```

**Interpretation:** The customer node successfully submitted a job to the hub's coordinator-api. The hub's coordinator-api can reach its own blockchain node via `settings.blockchain_rpc_url` for any settlement/governance queries triggered by this job.

### Step 7: Query the Hub's Bridge RPC from the Customer Node

On the **customer node**:

```bash
# Check bridge health on the hub
curl -s http://hub.aitbc.bubuit.net:8202/rpc/bridge/health | python3 -m json.tool

# Test bridge input validation (B13) from the customer node
curl -s -w "\nHTTP %{http_code}" -X POST http://hub.aitbc.bubuit.net:8202/rpc/bridge/lock \
  -H "Content-Type: application/json" \
  -d '{"target_chain":"","sender":"0xabc","recipient":"0xdef","amount":10,"signature":"0x123"}'
```

**Expected output:**

```json
{
  "success": true,
  "status": "healthy",
  "bridge_initialized": true,
  ...
}
{"detail":[{"type":"string_too_short","loc":["body","target_chain"],...}]}
HTTP 422
```

**Interpretation:** The customer node can reach the hub's bridge RPC, and the B13 input validation (from Scenario 22) works across the network.

### Step 8: Trade on the Hub's Exchange from the Customer Node

On the **customer node**:

```bash
# Query the hub's exchange orderbook
curl -s http://hub.aitbc.bubuit.net:8106/v1/exchange/orderbook | python3 -m json.tool | head -20

# Place a buy order on the hub's exchange
curl -s -X POST http://hub.aitbc.bubuit.net:8106/v1/exchange/orders \
  -H "Content-Type: application/json" \
  -d '{"order_type":"BUY","amount":1,"price":1.0,"user_address":"0xCustomer1"}'
```

**Expected output:**

```json
{
  "buy_orders": [...],
  "sell_orders": [...]
}
{"success": true, "order": {"id": ..., "order_type": "BUY", ...}}
```

**Interpretation:** The customer node successfully queried and traded on the hub's exchange.

### Step 9: Verify Hub-Side Logs Show the Cross-Node Requests

On the **hub node**:

```bash
# Check coordinator-api logs for the customer node's job submission
journalctl -u aitbc-coordinator-api --since "5 min ago" --no-pager | grep -iE "job|submit|customer"

# Check blockchain-node logs for bridge queries from the customer node
journalctl -u aitbc-blockchain-rpc --since "5 min ago" --no-pager | grep -iE "bridge|lock"

# Check exchange logs for the customer node's trade
journalctl -u aitbc-exchange --since "5 min ago" --no-pager | grep -iE "order|BUY"
```

---

## Code Examples

### A6 Fix: Settlement Hooks Use Configured URL

```python
# apps/coordinator-api/src/app/settlement/hooks.py — A6 fix
async def _get_current_chain_id(self) -> int:
    try:
        import httpx
        # Before A6: url = "http://localhost:8202/rpc/chain"
        response = httpx.get(f"{settings.blockchain_rpc_url}/rpc/chain")
        if response.status_code == 200:
            return response.json().get("chain_id", 1)
    except Exception as e:
        logger.warning("Failed to get chain ID: %s", e)
```

### A6 Fix: Governance Service Uses Env Var

```python
# apps/coordinator-api/src/app/contexts/governance/services/governance_service.py — A6 fix
# Before A6: url = "http://localhost:8202"
blockchain_rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
response = httpx.get(f"{blockchain_rpc_url}/rpc/accounts/{address}")
```

### CLI Config: Customer Node Override via Env Vars

```python
# cli/aitbc_cli/config.py — pydantic_settings reads env vars automatically
class CLIConfig(BaseAITBCConfig):
    model_config = SettingsConfigDict(
        env_file=["/etc/aitbc/blockchain.env", "/etc/aitbc/node.env"],
        case_sensitive=False,
    )
    blockchain_rpc_url: str = Field(default="http://localhost:8202")
    agent_coordinator_url: str = Field(default="http://localhost:8107")
    # Setting BLOCKCHAIN_RPC_URL env var overrides the default
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Configure the AITBC CLI on a customer node to point at a remote hub
- Verify cross-network connectivity to all hub services
- Confirm the hub's coordinator-api uses `settings.blockchain_rpc_url` (A6) instead of hardcoded localhost
- Submit a job from the customer node to the hub's coordinator-api
- Query the hub's bridge RPC and exchange from the customer node
- Verify hub-side logs show the cross-node requests

---

## Validation

```bash
# On the customer node: verify all hub endpoints are reachable
for port in 8202 8203 8106 8107 8108; do
  curl -sf --max-time 5 "http://hub.aitbc.bubuit.net:$port/health" > /dev/null \
    && echo "Port $port: PASS" \
    || echo "Port $port: FAIL"
done

# On the hub node: verify A6 fix is deployed (no hardcoded localhost)
grep -r "localhost:8202" /opt/aitbc/apps/coordinator-api/src/app/settlement/ \
  /opt/aitbc/apps/coordinator-api/src/app/contexts/governance/services/governance_service.py \
  | grep -v "BLOCKCHAIN_RPC_URL\|blockchain_rpc_url\|#\|docstring\|comment" \
  | grep -v ".pyc"
# Expected: no output (all hardcoded URLs removed by A6)

# On the hub node: verify the customer node's job was received
journalctl -u aitbc-coordinator-api --since "10 min ago" --no-pager | grep -c "job_id"
# Expected: 1+ (at least one job submitted)
```

---

## Megaplan Status

This scenario has been refreshed to reflect the current codebase megaplan (hub `hub.aitbc` ↔ shop `aitbc3`).

- All examples use the current coordinator API path `/v1/jobs` and the authenticated coordinator (`Authorization: Bearer <JWT>`).
- The Agent SDK `ComputeConsumer` supports `auth_token` and `coordinator_url` in `create(...)`.
- The live two-node AI job flow has been validated end-to-end on the deployed hub and shop nodes.
- The megaplan test suite is green: **0 failures**, **0 skipped**, and **4 expected xfails** for removed BlockSearch/TransactionSearch model tests.


## Related Resources

- [Service Ports Reference](../reference/SERVICE_PORTS.md)
- [v0.10.3 Change Log](../releases/v0.10.3/change.log)
- [Next Scenario: Fire-and-Forget Logging (B10/B11)](./35_fire_and_forget_logging_b10_b11.md)

---

*Last updated: 2026-08-20*
*Version: 1.2*
