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
systemctl start aitbc-blockchain-p2p.service   # hub only — not installed on followers
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
| Sync baseline stuck at wrong height | Force-sync requires an admin signature: POST `/rpc/force-sync` with `{"peer_url":"http://hub.aitbc.bubuit.net:8202","admin_address":"<admin>","admin_signature":"<sig>"}` — a bare curl returns 403 |
| Services fail with "resources" | `systemctl reset-failed` then restart |
| Following the wrong chain | Check `CHAIN_ID` and `default_peer_rpc_url` in `blockchain.env`/`node.env` (the legacy `SYNC_*` env vars and `aitbc-blockchain-sync.service` no longer exist) |

## Agent Config (in /etc/aitbc/node.env)

Read by `agent_stream.py` / `agent_task poll` — the old `AGENT_AGENT_IDS` /
`ENABLE_AGENT_POLLING` / `AGENT_SERVICE_URL` set is dead (nothing reads it):

```
AGENT_ID=my-agent                                  # or HERMES_AGENT_ID (fallback)
AGENT_COORDINATOR_URL=http://hub.aitbc.bubuit.net:8107  # or HERMES_COORDINATOR_URL
AITBC_DEFAULT_WALLET=my-agent-wallet               # wallet signing inbox polls
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
- `proposer_id` (PoA proposer address for block-producing nodes)
