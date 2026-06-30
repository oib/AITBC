# v0.5.10 Hub Migration — Follower Node Instructions

**Last Updated**: 2026-06-30
**Version**: 1.0

Followers do **NOT** run the migration script. They wipe their local chain.db and re-sync from the hub.

> **Critical lessons from the 2026-06-23 migration:**
> 1. **Followers MUST wipe chain.db** — flushing Redis alone is not enough. The local DB has stale pre-fork data and the node will think it's "up to date" by comparing against itself.
> 2. **`default_peer_rpc_url` must point to the hub** — if it points to `http://127.0.0.1:8202`, the follower syncs from itself. Check `/etc/aitbc/blockchain.env` and fix if needed.
> 3. **`aitbc-blockchain-rpc` must be restarted** — it's a separate service that caches DB connections. If not restarted, it will return stale height/state root even after the node has synced the new chain.
> 4. **Not all services exist on all nodes** — follower/shop nodes may not have `aitbc-agent-coordinator` or `aitbc-bridge-monitor`. Only stop/restart services that exist.

## Follower Step 1. Update code

```bash
cd /opt/aitbc
git pull
# Verify v0.5.10 code
test -f /opt/aitbc/aitbc/utils/units.py && echo "OK: units.py" || echo "MISSING: units.py"
grep -n "fee.*=.*36" /opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/transactions.py
# Expected: fee: int = 36
```

## Follower Step 2. Verify sync source points to hub

```bash
# Check that default_peer_rpc_url points to the hub, NOT localhost
grep "default_peer_rpc_url" /etc/aitbc/blockchain.env

# If it says http://127.0.0.1:8202, fix it:
# sed -i 's|default_peer_rpc_url=http://127.0.0.1:8202|default_peer_rpc_url=https://hub.aitbc.bubuit.net|' /etc/aitbc/blockchain.env

# Expected: default_peer_rpc_url=https://hub.aitbc.bubuit.net
```

- [ ] `default_peer_rpc_url` points to hub

## Follower Step 3. Stop all services

```bash
# Stop RPC first (releases DB connection), then node
systemctl stop aitbc-blockchain-rpc 2>/dev/null || true
systemctl stop aitbc-blockchain-explorer 2>/dev/null || true
systemctl stop aitbc-bridge-monitor 2>/dev/null || true
systemctl stop aitbc-wallet 2>/dev/null || true
systemctl stop aitbc-agent-coordinator 2>/dev/null || true
systemctl stop aitbc-blockchain-node

# Verify
ps aux | grep aitbc_chain | grep -v grep
# Should be empty
```

## Follower Step 4. Wipe local chain.db and flush Redis

```bash
DATA_DIR=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net
TS=$(date -u +%Y%m%d_%H%M%S)

# Backup the old chain.db (just in case)
mv "$DATA_DIR/chain.db" "$DATA_DIR/chain.db.pre-fork.$TS" 2>/dev/null || true
mv "$DATA_DIR/chain.db-wal" "$DATA_DIR/chain.db-wal.pre-fork.$TS" 2>/dev/null || true
mv "$DATA_DIR/chain.db-shm" "$DATA_DIR/chain.db-shm.pre-fork.$TS" 2>/dev/null || true

# Flush Redis (stale cached balances)
redis-cli FLUSHDB
redis-cli DBSIZE
# Expected: 0

# Verify chain.db is gone
ls "$DATA_DIR"/chain.db 2>/dev/null && echo "WARNING: chain.db still exists" || echo "OK: chain.db wiped"
```

- [ ] chain.db wiped
- [ ] Redis flushed (0 keys)

## Follower Step 5. Restart services

```bash
# Start node first — it will create a fresh chain.db and sync from hub
systemctl start aitbc-blockchain-node
sleep 5
systemctl is-active aitbc-blockchain-node && echo "blockchain-node: active" || echo "blockchain-node: FAILED"

# Start RPC server (fresh DB connection)
systemctl start aitbc-blockchain-rpc 2>/dev/null || true
sleep 3
systemctl is-active aitbc-blockchain-rpc 2>/dev/null && echo "blockchain-rpc: active" || echo "blockchain-rpc: not installed"

# Start other services
systemctl start aitbc-blockchain-explorer 2>/dev/null || true
systemctl start aitbc-wallet 2>/dev/null || true
systemctl start aitbc-agent-coordinator 2>/dev/null || true
systemctl start aitbc-bridge-monitor 2>/dev/null || true
```

## Follower Step 6. Wait for sync to complete

The node will bulk-import all blocks from the hub. This may take 1-5 minutes depending on chain length and network speed.

```bash
# Watch the sync progress in logs
journalctl -u aitbc-blockchain-node -f --no-pager | grep -E "Imported|bulk|Already|up to date"
# Wait until you see "Already up to date" or "Bulk import completed"
# Press Ctrl+C to exit the log stream

# Check sync height vs hub
FOLLOWER_HEIGHT=$(curl -s http://localhost:8202/rpc/head 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('height',0))" 2>/dev/null || echo 0)
HUB_HEIGHT=$(curl -s https://hub.aitbc.bubuit.net/rpc/head | python3 -c "import sys,json; print(json.load(sys.stdin).get('height',0))")
echo "Follower: $FOLLOWER_HEIGHT  Hub: $HUB_HEIGHT"
# They should match (or follower within 1-2 blocks of hub)
```

## Follower Step 7. Verify migration

```bash
# State root should match hub
FOLLOWER_ROOT=$(curl -s "http://localhost:8202/rpc/state/snapshot?chain_id=ait-hub.aitbc.bubuit.net" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state_root',''))")
HUB_ROOT=$(curl -s "https://hub.aitbc.bubuit.net/rpc/state/snapshot?chain_id=ait-hub.aitbc.bubuit.net" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state_root',''))")
echo "Follower: $FOLLOWER_ROOT"
echo "Hub:      $HUB_ROOT"
# They must match

# Balances should be in seconds (large numbers, multiples of 3600)
curl -s "http://localhost:8202/rpc/account/<your_address>" | python3 -m json.tool
# Balance should be a large number (seconds), not a small AIT number

# Verify via database directly (if RPC is stale)
sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
  'SELECT address, balance, balance / 3600.0 AS ait FROM account ORDER BY balance DESC LIMIT 3;'
```

- [ ] Follower height matches hub
- [ ] Follower state root matches hub
- [ ] Balances are in seconds (multiples of 3600)

## Follower Troubleshooting

**RPC returns stale height/state root after sync:**
The `aitbc-blockchain-rpc` service has a cached DB connection. Restart it:
```bash
systemctl restart aitbc-blockchain-rpc
sleep 3
curl -s http://localhost:8202/rpc/head | python3 -m json.tool
```

**Node says "Already up to date" but height is wrong:**
Check `default_peer_rpc_url` in `/etc/aitbc/blockchain.env`. If it points to `http://127.0.0.1:8202`, the node is syncing from itself. Fix it to `https://hub.aitbc.bubuit.net`, then wipe chain.db and restart.

**Node is not syncing at all:**
Check logs for errors:
```bash
journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep -E "Error|error|WARN|Failed|failed"
```
Verify the hub is reachable: `curl -s https://hub.aitbc.bubuit.net/rpc/head | python3 -m json.tool`

## Related Topics

- [Overview](./overview.md) - Migration overview
- [Migration Steps](./migration-steps.md) - Hub migration procedure
- [Troubleshooting](./troubleshooting.md) - Common issues and solutions

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.10 — Hub Migration Runbook
