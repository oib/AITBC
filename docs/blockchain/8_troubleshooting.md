# Troubleshooting

**Last Updated:** 2026-09-16

Common issues and solutions for blockchain nodes.

The diagnostics toolbox is **journald + the RPC API + `aitbc blockchain`**.
There are no `diagnose`, `config validate`, `reset`, `peers`, `sync --force`,
or `test-connectivity` subcommands — work through the tools below.

## First Response

```bash
# 1. Is the service up?
systemctl status aitbc-blockchain-node aitbc-blockchain-rpc

# 2. What do the logs say?
journalctl -u aitbc-blockchain-node --since "15 min ago" -p err
journalctl -u aitbc-blockchain-node -f          # follow live

# 3. What does the node report?
curl -s http://localhost:8202/rpc/status
curl -s http://localhost:8202/health
aitbc blockchain height
aitbc blockchain sync-status
```

## Common Issues

### Node Won't Start

**Check:**

```bash
systemctl status aitbc-blockchain-node
journalctl -u aitbc-blockchain-node -n 200 --no-pager
```

**Common causes and fixes:**

- **Port already in use** — `ss -tlnp | grep -E '8202|8200|9009'`; stop the
  conflicting process or change `RPC_BIND_PORT`/`P2P_BIND_PORT` in
  `/etc/aitbc/blockchain.env` and restart.
- **Bad env value** — pydantic-settings fails loudly at import; the journal
  shows a `ValidationError` naming the field. Fix the value in
  `/etc/aitbc/blockchain.env` or `node.env` (remember keys are
  case-insensitive — don't write `PROPOSER_ID` and `proposer_id` twice).
- **Missing proposer key** — `Failed to load proposer key from keystore`
  means `proposer_id` doesn't match `keystore/proposer.json`; on a follower,
  clear `proposer_id`/`enable_block_production=false` instead.
- **Corrupted database** — see *Database Corruption* below.

### Sync Stuck / Falling Behind

Followers sync via the hub subscription plus automatic bulk pull-sync — no
manual resync command exists.

**Check:**

```bash
# Compare local height against the hub
aitbc blockchain height
curl -s https://hub.aitbc.bubuit.net/rpc/head | jq .height

# Is the subscription lease active? (run on the hub)
curl -s http://localhost:8202/rpc/subscribers | jq

# Follower-side: watch the subscribe/heartbeat loop
journalctl -u aitbc-blockchain-node -f | grep -iE "subscri|heartbeat|lease|bulk"
```

**Common causes and fixes:**

- **Subscribe rejected (403)** — the follower's `BLOCKCHAIN_RPC_API_KEY` is not
  in the hub's `BLOCKCHAIN_RPC_API_KEY_PEERS`. Add it on the hub and restart
  `aitbc-blockchain-rpc` there.
- **`PROPOSER_ID` copied from the hub** — a follower filters gossip by its own
  proposer id; if it matches the hub's, every pushed block is discarded as
  self-proposed. The node then only catches up in bursts via bulk sync. Set a
  unique `proposer_id` (or leave it empty) in the follower's `node.env`.
- **`DEFAULT_PEER_RPC_URL` wrong** — must be the hub *base* URL
  (`https://hub.aitbc.bubuit.net`), no `/rpc` suffix.
- **Sync disabled** — verify `SYNC_MANAGER_ENABLED=true`,
  `SUBSCRIPTION_ENABLED=true`, `AUTO_SYNC_ENABLED=true`.
- **Gap keeps exceeding the sync** — check `auto_sync_threshold` (default 10)
  and `min_bulk_sync_interval` (default 60s) aren't set too high.

### Node Produces No Blocks (hub)

```bash
journalctl -u aitbc-blockchain-node -f | grep -iE "propos|block"
```

- `ENABLE_BLOCK_PRODUCTION=false` (or left unset on the hub) — set it `true`.
- `PROPOSER_ID` missing/invalid — must be the full 40-hex `0x` address that
  matches `keystore/proposer.json`.
- `BLOCK_PRODUCTION_CHAINS` set but not containing the chain.
- MV-PoA enabled without a `VALIDATOR_SET`, or fewer than
  `MULTI_VALIDATOR_MIN_ATTESTATIONS` validators reachable — check
  `aitbc blockchain consensus status`.

### Peer/Subscription Connection Issues

```bash
# Can the follower reach the hub at all?
curl -s https://hub.aitbc.bubuit.net/rpc/status

# Is the API key accepted?
curl -s -X POST https://hub.aitbc.bubuit.net/rpc/subscribe \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"node_id":"test","transport":"websocket","chain_id":"ait-hub.aitbc.bubuit.net"}'
```

- **403 on subscribe** — key not in `BLOCKCHAIN_RPC_API_KEY_PEERS` on the hub.
- **Timeouts** — outbound 443 blocked on the follower, or nginx/the hub is down.
- **Lease expires repeatedly** — heartbeat failures; check
  `heartbeat_interval` (default 60s) vs. `lease_duration` (default 3600s).

### High CPU/Memory Usage

```bash
systemctl status aitbc-blockchain-node   # shows current Memory/CPU vs limits
journalctl -u aitbc-blockchain-node --since "1 hour ago" -p warning
curl -s http://localhost:9009/metrics | grep -E 'process_|rpc_'
```

- Units are capped (`MemoryMax`, `CPUQuota` in the service files); an OOM kill
  shows as `Main process exited, code=killed, status=9/KILL` in the journal.
- A hot resync loop raises CPU — check for repeating bulk-sync lines and look
  at `auto_sync_max_retries`/`min_bulk_sync_interval`.

### Database Corruption

Chain data is SQLite at `<AITBC_DATA_DIR>/data/<chain_id>/chain.db` (live
fleet: `/var/lib/aitbc/data/<chain_id>/chain.db`). There is no `~/.aitbc`
directory and no `reset --hard` command.

```bash
# Integrity check
sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db "PRAGMA integrity_check;"
```

**Recovery options, least destructive first:**

1. **Let auto-sync repair** — if the local head diverged, `auto_resync_*`
   settings already trigger a re-sync from `default_peer_rpc_url` after
   consecutive rejections.
2. **Admin-signed force sync** — pull a trusted peer's full export:

   ```bash
   curl -X POST http://localhost:8202/rpc/force-sync \
     -H "Content-Type: application/json" \
     -d '{"peer_url":"https://hub.aitbc.bubuit.net",
          "admin_address":"0x<admin>",
          "admin_signature":"0x<signature over the body>"}'
   ```

3. **Manual reseed** — stop the node, move the bad `chain.db` aside, copy the
   correct `genesis.json` into `data/<chain_id>/`, restart; the node rebuilds
   via export/import or bulk sync:

   ```bash
   systemctl stop aitbc-blockchain-node
   mv /var/lib/aitbc/data/<chain_id>/chain.db /var/lib/aitbc/data/<chain_id>/chain.db.bad
   systemctl start aitbc-blockchain-node
   ```

4. **Restore from backup** — `aitbc blockchain restore --backup-file <backup> --verify`
   or `POST /rpc/import-chain` with an admin-signed export.

### Configuration Mistakes

There is no `config validate` command — misconfiguration surfaces as a
pydantic `ValidationError` at service start. Read it from the journal:

```bash
journalctl -u aitbc-blockchain-node -n 50 --no-pager | grep -A5 ValidationError
```

Common traps:

- `PROPOSER_ID` written twice in different cases — the lowercase spelling wins.
- `DEFAULT_PEER_RPC_URL` ending in `/rpc` — it must be a base URL.
- `VALIDATOR_SET`/`VALIDATOR_KEYS` malformed JSON — quote them as single-line
  JSON in the env file.

## Recovery Procedures

### Complete Node Recovery (follower)

```bash
# 1. Stop services
systemctl stop aitbc-blockchain-rpc aitbc-blockchain-node

# 2. Preserve state
aitbc blockchain backup --chain-id <chain> --path /backup/pre-recovery.tar.gz --compress
mv /var/lib/aitbc/data/<chain_id>/chain.db{,.bad}   # if corrupt

# 3. Fix env, restore or reseed genesis, then start
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc

# 4. Watch catch-up
journalctl -u aitbc-blockchain-node -f
aitbc blockchain sync-status
```

## Best Practices

### Prevention

1. **Watch `journalctl -u aitbc-blockchain-node` after every config change**
2. **Back up chain DBs** before upgrades (`aitbc blockchain backup --verify`)
3. **Keep env files minimal** — one spelling per key, no stale vars
4. **Alert on height lag** via the coordinator's metrics/alerts pipeline
   (see [7_monitoring.md](./7_monitoring.md))

### Troubleshooting Workflow

1. `systemctl status` — is it running?
2. `journalctl -u aitbc-blockchain-node -p err` — what does it say?
3. `curl /rpc/status` + `aitbc blockchain sync-status` — where is the chain?
4. Fix env → `systemctl restart` → watch the journal.

## Next

- [Operations](./3_operations.md) — Day-to-day operations
- [Configuration](./2_configuration.md) — Node configuration
- [Monitoring](./7_monitoring.md) — Monitoring and alerting
