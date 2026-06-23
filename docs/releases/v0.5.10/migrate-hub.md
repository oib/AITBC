# v0.5.10 Hub Migration Runbook

**Node**: `hub.aitbc.bubuit.net` (PoA authority)
**Chain ID**: `ait-hub.aitbc.bubuit.net`
**Date**: 2026-06-23
**Operator**: _________________

This is the step-by-step runbook for migrating the **hub node** to v0.5.10. The hub is the PoA authority — all follower nodes sync from it. The hub must migrate first; followers re-sync afterwards.

> **Breaking change.** All nodes must run v0.5.10 code. A node still on v0.5.9 will reject fee=36 transactions and vice versa.

> **Lessons learned.** This runbook was updated after the actual migration on 2026-06-23. Key findings:
> - **Hub has more services than expected** — `aitbc-blockchain-rpc` is a separate service from `aitbc-blockchain-node` and must be stopped/restarted too. See Step 2 and Step 8.
> - **Follower nodes must wipe chain.db** — flushing Redis alone is not enough. The local DB has stale pre-fork data and the node will think it's "up to date" by comparing against itself. See Follower Node Instructions.
> - **Follower `default_peer_rpc_url` must point to the hub** — if it points to `localhost`, the follower syncs from itself and never receives the migrated state. See Follower Node Instructions.
> - **Follower `aitbc-blockchain-rpc` must be restarted** — it caches DB connections and will return stale height/state root after chain.db is wiped. See Follower Node Instructions.
> - **State root from migration script differs from node's** — the script uses a simplified SHA-256 hash; the node uses its real MPT implementation. The node's state root is authoritative. See Troubleshooting.

---

## Pre-flight Checks

Complete these **before** the maintenance window. All items must pass.

### P1. Code is deployed

```bash
# Confirm v0.5.10 code is on the hub
cd /opt/aitbc
git log --oneline -1
# Expected: a commit with v0.5.10 changes

# Confirm key files exist
test -f /opt/aitbc/aitbc/utils/units.py && echo "OK: units.py" || echo "MISSING: units.py"
test -f /opt/aitbc/scripts/migration/scale_balances_3600x.py && echo "OK: migration script" || echo "MISSING: migration script"
test -x /opt/aitbc/scripts/migration/scale_balances_3600x.py && echo "OK: executable" || echo "NOT EXECUTABLE"

# Confirm fee default is 36 (not 10)
grep -n "fee.*=.*36" /opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/transactions.py
# Expected: fee: int = 36
```

- [ ] Code deployed and verified

### P2. Services are currently running

```bash
# List all aitbc services on this node
systemctl list-units --type=service | grep aitbc

# Check the key services (hub typically has all of these)
systemctl is-active aitbc-blockchain-node
systemctl is-active aitbc-blockchain-rpc
systemctl is-active aitbc-blockchain-explorer
systemctl is-active aitbc-agent-coordinator
systemctl is-active aitbc-wallet
systemctl is-active aitbc-bridge-monitor
# All should report "active" (some may be "inactive" if not installed)
```

- [ ] All installed services active
- [ ] Record which services are present: _________________

### P3. Database is accessible and has data

```bash
CHAIN_DB=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db

# Confirm file exists
ls -lh "$CHAIN_DB"

# Count rows (quote "transaction" — it's a SQL keyword)
sqlite3 "$CHAIN_DB" 'SELECT COUNT(*) FROM account;'
sqlite3 "$CHAIN_DB" 'SELECT COUNT(*) FROM "transaction";'
sqlite3 "$CHAIN_DB" 'SELECT COUNT(*) FROM block;'
sqlite3 "$CHAIN_DB" 'SELECT COUNT(*) FROM mempool;'

# Sample a balance to verify pre-migration state
sqlite3 "$CHAIN_DB" 'SELECT address, balance FROM account ORDER BY balance DESC LIMIT 3;'
```

- [ ] Database accessible, row counts recorded
- [ ] Pre-migration sample balances recorded: _________________

### P4. Disk space for backups

```bash
# Need at least 2x chain.db size for backups
CHAIN_DB=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db
df -h "$(dirname "$CHAIN_DB")"
du -sh "$CHAIN_DB"
```

- [ ] Sufficient disk space (≥ 2× chain.db size free)

### P5. Genesis file exists

```bash
GENESIS=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/genesis.json
cat "$GENESIS" | python3 -m json.tool
```

- [ ] genesis.json present and valid JSON

### P6. Redis is running

```bash
redis-cli ping
# Expected: PONG
```

- [ ] Redis responding

### P7. Notify follower operators

All follower node operators must be notified of the fork time. Followers do NOT run the migration script — they update code, flush Redis, and re-sync from the hub.

- [ ] Follower operators notified of fork time: _________________

---

## Migration Steps

Execute these in order during the maintenance window. Do not skip steps.

### Step 1. Announce maintenance start

```bash
echo "[$(date -u)] v0.5.10 hub migration STARTED" | tee -a /var/log/aitbc-migration.log
```

- [ ] Logged

### Step 2. Stop all services

> **Critical:** `aitbc-blockchain-rpc` is a **separate service** from `aitbc-blockchain-node`.
> It runs its own uvicorn process with its own DB connection. If it's not stopped,
> it will hold a stale database connection and return pre-migration data after restart.
> Stop it first so it releases the DB lock before the migration script runs.

```bash
# Stop in reverse dependency order — RPC and explorer first, then node
systemctl stop aitbc-blockchain-explorer
systemctl stop aitbc-blockchain-rpc
systemctl stop aitbc-bridge-monitor
systemctl stop aitbc-wallet
systemctl stop aitbc-agent-coordinator
systemctl stop aitbc-blockchain-node

# Also stop the sync service if it exists (it may interfere with bulk import)
systemctl stop aitbc-blockchain-sync 2>/dev/null || true

# Verify all stopped
for svc in aitbc-blockchain-node aitbc-blockchain-rpc aitbc-blockchain-explorer \
           aitbc-agent-coordinator aitbc-wallet aitbc-bridge-monitor; do
    state=$(systemctl is-active "$svc" 2>/dev/null)
    echo "$svc: $state"
done
# All should report "inactive" or "not-found"
```

- [ ] All services stopped (including blockchain-rpc)
- [ ] No aitbc processes still running: `ps aux | grep aitbc_chain | grep -v grep`

### Step 3. Manual backup (in addition to script backup)

```bash
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
DATA_DIR=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net

cp "$DATA_DIR/chain.db" "$DATA_DIR/chain.db.pre-fork.$TIMESTAMP"
cp "$DATA_DIR/genesis.json" "$DATA_DIR/genesis.json.pre-fork.$TIMESTAMP"

# Also back up the WAL and SHM files if they exist
cp "$DATA_DIR/chain.db-wal" "$DATA_DIR/chain.db-wal.pre-fork.$TIMESTAMP" 2>/dev/null || true
cp "$DATA_DIR/chain.db-shm" "$DATA_DIR/chain.db-shm.pre-fork.$TIMESTAMP" 2>/dev/null || true

ls -lh "$DATA_DIR"/*.pre-fork.*
```

- [ ] Backups created and verified
- [ ] Backup filenames: _________________

### Step 4. Run the migration script

```bash
cd /opt/aitbc
python3 scripts/migration/scale_balances_3600x.py \
  --chain-id ait-hub.aitbc.bubuit.net \
  --data-path /var/lib/aitbc/data
```

**Expected output:**
```
🚀 Starting v0.5.10 hard fork migration for chain: ait-hub.aitbc.bubuit.net
💾 Creating backups...
✅ Backed up chain.db -> ...
✅ Backed up genesis.json -> ...

📊 Scaling on-chain data...
  ✅ Updated N account balances
  ✅ Updated N transactions (value and fee)
  ✅ Updated N receipt minted amounts
  ✅ Updated N escrow amounts
  ✅ Updated N cross-chain transfer amounts
  ✅ Updated N stake amounts
  ✅ Cleared N pending transactions from mempool

🔐 Recalculating state root...
  ✅ New state root: <hash>
  ✅ Updated genesis block state_root in database

🔍 Verifying migration...
  Sample account balances: ...
  Sample transaction fees: ...
  Genesis block state_root: <hash>

✅ Migration completed successfully!
```

- [ ] Script completed without errors
- [ ] All 6 tables updated
- [ ] Mempool cleared
- [ ] State root recalculated: _________________

### Step 5. Verify migration results

```bash
CHAIN_DB=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db

# All balances should now be multiples of 3600
sqlite3 "$CHAIN_DB" 'SELECT address, balance, balance / 3600.0 AS ait FROM account ORDER BY balance DESC LIMIT 5;'

# All transaction fees should be multiples of 3600 (pre-fork fee=10 → 36000)
sqlite3 "$CHAIN_DB" 'SELECT tx_hash, fee, fee / 3600.0 AS ait FROM "transaction" ORDER BY created_at DESC LIMIT 5;'

# Mempool should be empty
sqlite3 "$CHAIN_DB" 'SELECT COUNT(*) FROM mempool;'
# Expected: 0

# No sub-AIT balances should exist (balance < 3600 and > 0)
sqlite3 "$CHAIN_DB" 'SELECT COUNT(*) FROM account WHERE balance > 0 AND balance < 3600;'
# Expected: 0

# Genesis block state_root should be updated
sqlite3 "$CHAIN_DB" 'SELECT height, state_root FROM block WHERE height = 0;'
```

- [ ] Balances are multiples of 3600
- [ ] Fees are multiples of 3600
- [ ] Mempool is empty (0 rows)
- [ ] No sub-AIT balances (0 rows)
- [ ] Genesis block state_root updated

### Step 6. Verify genesis.json was scaled

```bash
GENESIS=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/genesis.json
python3 -c "
import json
with open('$GENESIS') as f:
    g = json.load(f)
print('Chain ID:', g['chain_id'])
print('State root:', g['block']['state_root'])
print('Allocations:')
for a in g.get('allocations', []):
    ait = a['balance'] / 3600
    print(f'  {a[\"address\"]}: {a[\"balance\"]} seconds ({ait:.0f} AIT)')
if not g.get('allocations'):
    print('  (no allocations — balances are in account table)')
"
```

- [ ] genesis.json state_root matches database
- [ ] Allocations scaled (if any)

### Step 7. Flush Redis cache

```bash
redis-cli FLUSHDB
# Expected: OK

# Verify cache is empty
redis-cli DBSIZE
# Expected: 0
```

- [ ] Redis flushed
- [ ] Cache size is 0

### Step 8. Restart services

> **Critical:** Restart `aitbc-blockchain-node` first and wait for it to initialize,
> then restart `aitbc-blockchain-rpc`. The RPC server needs a fresh DB connection
> to the migrated database — if it was not stopped in Step 2, it will return stale data.

```bash
systemctl start aitbc-blockchain-node
sleep 5
systemctl is-active aitbc-blockchain-node && echo "blockchain-node: active" || echo "blockchain-node: FAILED"

# Restart the RPC server (separate service with its own DB connection)
systemctl start aitbc-blockchain-rpc
sleep 3
systemctl is-active aitbc-blockchain-rpc && echo "blockchain-rpc: active" || echo "blockchain-rpc: FAILED"

systemctl start aitbc-blockchain-explorer
sleep 2
systemctl is-active aitbc-blockchain-explorer && echo "blockchain-explorer: active" || echo "blockchain-explorer: FAILED"

systemctl start aitbc-agent-coordinator
sleep 2
systemctl is-active aitbc-agent-coordinator && echo "agent-coordinator: active" || echo "agent-coordinator: FAILED"

systemctl start aitbc-wallet
sleep 2
systemctl is-active aitbc-wallet && echo "wallet: active" || echo "wallet: FAILED"

systemctl start aitbc-bridge-monitor
sleep 2
systemctl is-active aitbc-bridge-monitor && echo "bridge-monitor: active" || echo "bridge-monitor: FAILED"
```

- [ ] blockchain-node: active
- [ ] blockchain-rpc: active
- [ ] blockchain-explorer: active
- [ ] agent-coordinator: active (if installed)
- [ ] wallet: active
- [ ] bridge-monitor: active (if installed)

### Step 9. Post-migration verification

Wait 10 seconds for services to initialize, then verify:

```bash
# State root should match what the migration script calculated
curl -s http://localhost:8202/rpc/state/snapshot | python3 -m json.tool
# Record state_root: _________________

# Genesis account balance should be in seconds (very large number)
# Replace with actual genesis address
GENESIS_ADDR=$(sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db 'SELECT address FROM account ORDER BY balance DESC LIMIT 1;')
echo "Genesis address: $GENESIS_ADDR"
curl -s "http://localhost:8202/rpc/account/$GENESIS_ADDR" | python3 -m json.tool
# Balance should be a large number (seconds), e.g. 3600000000000

# Check that new transactions use fee=36
# (Submit a test transaction or check mempool acceptance)
```

- [ ] State root matches migration script output
- [ ] Genesis account balance is in seconds
- [ ] RPC responding correctly

### Step 10. Test a transaction (optional but recommended)

```bash
# Submit a small test transaction to verify fee=36 is accepted
# Use the CLI or curl — adjust addresses as needed

# Via CLI:
# aitbc wallet send --to <test_address> --amount 0.01 --fee 0.01
# This sends amount=36 seconds, fee=36 seconds to the blockchain

# Verify the transaction was accepted
curl -s http://localhost:8202/rpc/head | python3 -m json.tool
# Block height should advance
```

- [ ] Test transaction accepted
- [ ] Block height advanced

### Step 11. Announce migration complete

```bash
echo "[$(date -u)] v0.5.10 hub migration COMPLETED. State root: $(curl -s http://localhost:8202/rpc/state/snapshot | python3 -c 'import sys,json; print(json.load(sys.stdin).get("state_root","unknown"))')" | tee -a /var/log/aitbc-migration.log
```

- [ ] Completion logged
- [ ] Follower operators notified to proceed with their steps

---

## Follower Node Instructions (send to all follower operators)

Followers do **NOT** run the migration script. They wipe their local chain.db and re-sync from the hub.

> **Critical lessons from the 2026-06-23 migration:**
> 1. **Followers MUST wipe chain.db** — flushing Redis alone is not enough. The local DB has stale pre-fork data and the node will think it's "up to date" by comparing against itself.
> 2. **`default_peer_rpc_url` must point to the hub** — if it points to `http://127.0.0.1:8202`, the follower syncs from itself. Check `/etc/aitbc/blockchain.env` and fix if needed.
> 3. **`aitbc-blockchain-rpc` must be restarted** — it's a separate service that caches DB connections. If not restarted, it will return stale height/state root even after the node has synced the new chain.
> 4. **Not all services exist on all nodes** — follower/shop nodes may not have `aitbc-agent-coordinator` or `aitbc-bridge-monitor`. Only stop/restart services that exist.

### Follower Step 1. Update code

```bash
cd /opt/aitbc
git pull
# Verify v0.5.10 code
test -f /opt/aitbc/aitbc/utils/units.py && echo "OK: units.py" || echo "MISSING: units.py"
grep -n "fee.*=.*36" /opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/transactions.py
# Expected: fee: int = 36
```

### Follower Step 2. Verify sync source points to hub

```bash
# Check that default_peer_rpc_url points to the hub, NOT localhost
grep "default_peer_rpc_url" /etc/aitbc/blockchain.env

# If it says http://127.0.0.1:8202, fix it:
# sed -i 's|default_peer_rpc_url=http://127.0.0.1:8202|default_peer_rpc_url=https://hub.aitbc.bubuit.net|' /etc/aitbc/blockchain.env

# Expected: default_peer_rpc_url=https://hub.aitbc.bubuit.net
```

- [ ] `default_peer_rpc_url` points to hub

### Follower Step 3. Stop all services

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

### Follower Step 4. Wipe local chain.db and flush Redis

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

### Follower Step 5. Restart services

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

### Follower Step 6. Wait for sync to complete

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

### Follower Step 7. Verify migration

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

### Follower Troubleshooting

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

---

## Rollback Procedure

If the migration fails or causes issues, roll back to pre-fork state:

```bash
# 1. Stop all services (RPC first to release DB)
systemctl stop aitbc-blockchain-rpc 2>/dev/null || true
systemctl stop aitbc-blockchain-explorer 2>/dev/null || true
systemctl stop aitbc-bridge-monitor 2>/dev/null || true
systemctl stop aitbc-wallet 2>/dev/null || true
systemctl stop aitbc-agent-coordinator 2>/dev/null || true
systemctl stop aitbc-blockchain-node

# 2. Restore from backup (use the timestamp from Step 3)
TIMESTAMP=<timestamp from Step 3>
DATA_DIR=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net

cp "$DATA_DIR/chain.db.pre-fork.$TIMESTAMP" "$DATA_DIR/chain.db"
cp "$DATA_DIR/genesis.json.pre-fork.$TIMESTAMP" "$DATA_DIR/genesis.json"
# Remove WAL/SHM so SQLite doesn't try to replay old writes
rm -f "$DATA_DIR/chain.db-wal" "$DATA_DIR/chain.db-shm"

# 3. Flush Redis
redis-cli FLUSHDB

# 4. Roll back code to v0.5.9
cd /opt/aitbc
git checkout <v0.5.9 commit hash>

# 5. Restart services (node first, then RPC)
systemctl start aitbc-blockchain-node
sleep 3
systemctl start aitbc-blockchain-rpc 2>/dev/null || true
systemctl start aitbc-blockchain-explorer 2>/dev/null || true
systemctl start aitbc-agent-coordinator 2>/dev/null || true
systemctl start aitbc-wallet 2>/dev/null || true
systemctl start aitbc-bridge-monitor 2>/dev/null || true

# 6. Verify
curl -s http://localhost:8202/rpc/head | python3 -m json.tool
```

- [ ] Rollback tested in staging (recommended)

---

## Troubleshooting

### Migration script fails with "database is locked"

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

### Migration script fails with "near 'transaction': syntax error"

This was a bug in the migration script where the `transaction` table name (a SQL reserved keyword) was not quoted. **Fixed in commit `ff2176b6a`** — ensure you have the latest version:
```bash
cd /opt/aitbc
git pull
grep 'UPDATE "transaction"' scripts/migration/scale_balances_3600x.py
# Should show: UPDATE "transaction" SET value = value * 3600, fee = fee * 3600
```

### State root mismatch after restart

The state root reported by the migration script (`2d64cfa9...`) will differ from the state root reported by the running node (`0x5aee7550...`). This is expected — the migration script uses a simplified SHA-256 hash, while the node uses its real Merkle Patricia Trie implementation. **The node's state root is authoritative.**

To verify the migration is correct, check that:
1. Account balances are multiples of 3600
2. Transaction fees are multiples of 3600
3. No sub-AIT balances exist (`balance > 0 AND balance < 3600` → 0 rows)
4. The node's state root matches across restarts

### RPC returns stale height or state root after migration

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

### Follower nodes can't sync

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

### Follower RPC returns stale data after sync

Same as the hub issue — `aitbc-blockchain-rpc` caches DB connections. Restart it:
```bash
systemctl restart aitbc-blockchain-rpc
sleep 3
curl -s http://localhost:8202/rpc/head | python3 -m json.tool
```

### Genesis.json has empty allocations

If `genesis.json` shows `"allocations": []` (as seen on the hub), the genesis balances are stored in the `account` table, not in the genesis file. The migration script handles both cases — the `scale_genesis_json()` step will simply skip if allocations are empty, and the `scale_balances()` step handles the `account` table.

### Not all services exist on follower nodes

Follower/shop nodes may not have `aitbc-agent-coordinator`, `aitbc-bridge-monitor`, or other hub-specific services installed. Use `2>/dev/null || true` when stopping/starting to avoid errors, and check `systemctl list-units | grep aitbc` to see which services are present.

---

## Summary Checklist

| Step | Description | Done |
|------|-------------|------|
| P1 | Code deployed and verified | ☐ |
| P2 | Services running (including blockchain-rpc) | ☐ |
| P3 | Database accessible | ☐ |
| P4 | Disk space sufficient | ☐ |
| P5 | Genesis file present | ☐ |
| P6 | Redis running | ☐ |
| P7 | Followers notified | ☐ |
| 1 | Announce start | ☐ |
| 2 | Stop all services (including blockchain-rpc) | ☐ |
| 3 | Manual backup | ☐ |
| 4 | Run migration script | ☐ |
| 5 | Verify migration results | ☐ |
| 6 | Verify genesis.json | ☐ |
| 7 | Flush Redis | ☐ |
| 8 | Restart services (node first, then RPC) | ☐ |
| 9 | Post-migration verification | ☐ |
| 10 | Test transaction | ☐ |
| 11 | Announce complete | ☐ |

### Follower Checklist (for each follower operator)

| Step | Description | Done |
|------|-------------|------|
| F1 | Update code to v0.5.10 | ☐ |
| F2 | Verify `default_peer_rpc_url` points to hub | ☐ |
| F3 | Stop all services (including blockchain-rpc) | ☐ |
| F4 | Wipe chain.db + flush Redis | ☐ |
| F5 | Restart services (node first, then RPC) | ☐ |
| F6 | Wait for bulk sync from hub | ☐ |
| F7 | Verify state root matches hub | ☐ |
| F8 | Verify balances are in seconds | ☐ |

---

## Sign-off

### Hub Migration

- **Migration performed by**: _________________
- **Date**: _________________
- **Migration script state root**: _________________
- **Node state root (authoritative)**: _________________
- **All checks passed**: ☐ Yes ☐ No (explain: _________________)
- **Followers notified**: ☐

### Follower Migrations

| Follower Node | Operator | Synced | State Root Matches | Verified |
|---------------|----------|--------|-------------------|----------|
| _________________ | _________________ | ☐ | ☐ | ☐ |
| _________________ | _________________ | ☐ | ☐ | ☐ |
| _________________ | _________________ | ☐ | ☐ | ☐ |

---

## Post-Migration Notes (2026-06-23)

### What happened

**Hub migration** (performed on `hub.aitbc.bubuit.net`):
- Migration script ran successfully after fixing the `transaction` table quoting bug
- 11 accounts, 116 transactions, 10 escrows, 6 stakes scaled by 3600
- Mempool cleared, state root recalculated
- Node state root: `0x5aee7550...` (differs from script's `2d64cfa9...` — expected)
- All services restarted successfully

**Follower migration** (performed on `aitbc3` / shop node):
- Initial attempt with just Redis flush + restart failed — node synced from itself (`default_peer_rpc_url=http://127.0.0.1:8202`)
- Fixed `default_peer_rpc_url` to `https://hub.aitbc.bubuit.net` in `/etc/aitbc/blockchain.env`
- Wiped chain.db, flushed Redis, restarted — node bulk-synced 34,284 blocks from hub
- `aitbc-blockchain-rpc` was returning stale data (old height/state root) — restarted it separately
- Final state: follower height 34284 = hub height 34284, state roots match

### Config changes made

| Node | File | Change |
|------|------|--------|
| `aitbc3` (follower) | `/etc/aitbc/blockchain.env` | `default_peer_rpc_url`: `http://127.0.0.1:8202` → `https://hub.aitbc.bubuit.net` |

### Backups

| Node | Path | Timestamp |
|------|------|-----------|
| Hub | `/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db.pre-fork.*` | `20260623_160659` |
| Hub | `/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/genesis.json.pre-fork.*` | `20260623_160659` |
| Follower (`aitbc3`) | `/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db.pre-fork.*` | `20260623_161722` |
