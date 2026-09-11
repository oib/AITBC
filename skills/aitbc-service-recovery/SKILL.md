---
name: aitbc-service-recovery
description: AITBC systemd service recovery — relink, restart, and debug all AITBC services on `<node2>`
category: devops
---

# AITBC Service Recovery

## When to Use

After reboot, repo restructure, or when AITBC services are not running.

## Recovery Steps

### 1. Relink Systemd Services

```bash
bash /opt/aitbc/scripts/utils/link-systemd.sh
```

### 2. Load Keystore Secrets

```bash
bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh
```

### 3. Start Core Services

```bash
systemctl start aitbc-blockchain-rpc.service
systemctl start aitbc-blockchain-node.service
systemctl start aitbc-blockchain-p2p.service
systemctl start aitbc-blockchain-sync.service
systemctl start aitbc-wallet.service
systemctl start aitbc-coordinator-api.service
```

### 4. Start Agent Messaging

```bash
systemctl start aitbc-agent.service
```

## Common Failures

| Symptom | Fix |
|---------|-----|
| Wallet service: exit code, missing COORDINATOR_API_KEY | Add `echo "key" > /etc/aitbc/credentials/coordinator_api_key && chmod 600` |
| Sync service exits immediately | Add Agent vars to `/etc/aitbc/node.env` (see below) OR set `AGENT_DAEMON_CHAINS` |
| P2P immediate FIN from hub | `p2p_peers` must use port **7070** (not 8106 — that's Exchange API) |
| Sync baseline stuck at wrong height | Force-sync via blockchain rpc: `curl -X POST http://localhost:8202/rpc/force-sync -H 'Content-Type: application/json' -d '{"peer_url":"http://hub.aitbc.bubuit.net:8202"}'` |
| Services fail with "resources" | `systemctl reset-failed` then restart |
| Sync service wrong chain | Wrapper reads `SYNC_CHAIN_ID` not `CHAIN_ID` — check aitbc-blockchain-sync-wrapper.py |

## Agent Polling Config (in /etc/aitbc/node.env)

```
ENABLE_AGENT_POLLING=true
AGENT_AGENT_IDS=owl-aitbc3
AGENT_COORDINATOR_URL=http://hub.aitbc.bubuit.net:8107
AGENT_SERVICE_URL=http://localhost:8014  # check-ports: ignore
AGENT_AGENT_ID=owl-aitbc3
```

## Port Reference

| Port | Service |
|------|---------|
| 8202 | Blockchain RPC |
| 7070 | Blockchain P2P (use in p2p_peers) |
| 8106 | Exchange API |
| 8203 | Coordinator API |
| 8107 | Agent Coordinator |
| 8108 | Wallet Daemon |

## Credentials

Stored in `/etc/aitbc/credentials/`:
- `api_hash_secret`
- `keystore_password`
- `coordinator_api_key`
- `proposer_id` (sync service node ID)
