---
name: aitbc-service-recovery
description: AITBC systemd service recovery — relink, restart, and debug all AITBC services on aitbc3
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
| P2P immediate FIN from hub | `p2p_peers` must use port **7070** (not 8001 — that's Exchange API) |
| Sync baseline stuck at wrong height | Force-sync: `curl -X POST http://localhost:8006/rpc/force-sync -H 'Content-Type: application/json' -d '{"peer_url":"http://hub.aitbc.bubuit.net:8006"}'` |
| Services fail with "resources" | `systemctl reset-failed` then restart |
| Sync service wrong chain | Wrapper reads `SYNC_CHAIN_ID` not `CHAIN_ID` — check aitbc-blockchain-sync-wrapper.py |

## Agent Polling Config (in /etc/aitbc/node.env)

```
ENABLE_AGENT_POLLING=true
AGENT_AGENT_IDS=owl-aitbc3
AGENT_COORDINATOR_URL=http://hub.aitbc.bubuit.net:8011
AGENT_SERVICE_URL=http://localhost:8014
AGENT_AGENT_ID=owl-aitbc3
```

## Port Reference

| Port | Service |
|------|---------|
| 8006 | Blockchain RPC |
| 8001 | aitbc3 P2P listener |
| 7070 | Hub P2P (use in p2p_peers) |
| 8010 | Exchange API |
| 8011 | Coordinator API (Agent messaging) |
| 8014 | Agent Service |
| 8015 | Wallet Daemon |

## Credentials

Stored in `/etc/aitbc/credentials/`:
- `api_hash_secret`
- `keystore_password`
- `coordinator_api_key`
- `proposer_id` (sync service node ID)
