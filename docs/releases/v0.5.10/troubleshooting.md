# v0.5.10 Hub Migration — Troubleshooting

**Last Updated**: 2026-06-30
**Version**: 1.0

## Migration script fails with "database is locked"

The blockchain node or RPC server is still running and holding a DB connection:
```bash
# Stop ALL services that might hold a DB connection
systemctl stop aitbc-blockchain-rpc 2>/dev/null || true
systemctl stop aitbc-blockchain-node 2>/dev/null || true

# Wait for clean shutdown
sleep 5

# Kill any lingering processes
pkill -f "aitbc_chain" || true
pkill -f "uvicorn.*aitbc_chain" || true

# Verify no processes remain
ps aux | grep aitbc_chain | grep -v grep
# Should be empty

# Retry migration
```

## Migration script fails with "near 'transaction': syntax error"

This was a bug in the migration script where the `transaction` table name (a SQL reserved keyword) was not quoted. **Fixed in commit `ff2176b6a`** — ensure you have the latest version:
```bash
cd /opt/aitbc
git pull
grep 'UPDATE "transaction"' scripts/migration/scale_balances_3600x.py
# Should show: UPDATE "transaction" SET value = value * 3600, fee = fee * 3600
```

## State root mismatch after restart

The state root reported by the migration script (`2d64cfa9...`) will differ from the state root reported by the running node (`0x5aee7550...`). This is expected — the migration script uses a simplified SHA-256 hash, while the node uses its real Merkle Patricia Trie implementation. **The node's state root is authoritative.**

To verify the migration is correct, check that:
1. Account balances are multiples of 3600
2. Transaction fees are multiples of 3600
3. No sub-AIT balances exist (`balance > 0 AND balance < 3600` → 0 rows)
4. The node's state root matches across restarts

## RPC returns stale height or state root after migration

The `aitbc-blockchain-rpc` service runs a separate uvicorn process with its own database connection pool. If it was not stopped during Step 2, or not restarted during Step 8, it will return stale pre-migration data.

**Fix:** Restart the RPC service:
```bash
systemctl restart aitbc-blockchain-rpc
sleep 3
curl -s http://localhost:8202/rpc/head | python3 -m json.tool
# Height and state_root should now be correct
```

**Verify the DB directly if RPC still looks wrong:**
```bash
sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
  'SELECT height, state_root FROM block ORDER BY height DESC LIMIT 1;'
# If DB is correct but RPC is wrong, restart RPC again
```

## Follower nodes can't sync

If followers report sync errors or show wrong state root after the hub migrates:

1. **Check `default_peer_rpc_url`** in `/etc/aitbc/blockchain.env`:
   ```bash
   grep default_peer_rpc_url /etc/aitbc/blockchain.env
   # Must be: https://hub.aitbc.bubuit.net
   # NOT: http://127.0.0.1:8202 (this causes self-sync)
   ```

2. **Confirm follower is running v0.5.10 code:**
   ```bash
   grep "fee.*=.*36" /opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/transactions.py
   # Expected: fee: int = 36
   ```

3. **Wipe local chain.db and re-sync from scratch** (the most reliable fix):
   ```bash
   systemctl stop aitbc-blockchain-rpc 2>/dev/null || true
   systemctl stop aitbc-blockchain-node

   DATA_DIR=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net
   mv "$DATA_DIR/chain.db" "$DATA_DIR/chain.db.pre-fork.failed" 2>/dev/null || true
   rm -f "$DATA_DIR/chain.db-wal" "$DATA_DIR/chain.db-shm"

   redis-cli FLUSHDB

   systemctl start aitbc-blockchain-node
   # Wait for bulk sync to complete (watch logs)
   journalctl -u aitbc-blockchain-node -f | grep -E "Already|bulk|completed"
   # Press Ctrl+C when you see "Already up to date"

   systemctl start aitbc-blockchain-rpc 2>/dev/null || true
   ```

4. **Verify sync completed:**
   ```bash
   # Compare state roots
   curl -s "http://localhost:8202/rpc/state/snapshot?chain_id=ait-hub.aitbc.bubuit.net" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state_root'))"
   curl -s "https://hub.aitbc.bubuit.net/rpc/state/snapshot?chain_id=ait-hub.aitbc.bubuit.net" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state_root'))"
   # Must match
   ```

## Follower RPC returns stale data after sync

Same as the hub issue — `aitbc-blockchain-rpc` caches DB connections. Restart it:
```bash
systemctl restart aitbc-blockchain-rpc
sleep 3
curl -s http://localhost:8202/rpc/head | python3 -m json.tool
```

## Related Topics

- [Overview](./overview.md) - Migration overview
- [Migration Steps](./migration-steps.md) - Hub migration procedure
- [Follower Instructions](./follower-instructions.md) - Follower node procedures
- [Rollback](./rollback.md) - Rollback procedures

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.10 — Hub Migration Runbook
