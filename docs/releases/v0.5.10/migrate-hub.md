# v0.5.10 Hub Migration Runbook

**Node**: `hub.aitbc.bubuit.net` (PoA authority)
**Chain ID**: `ait-hub.aitbc.bubuit.net`
**Date**: 2026-06-23
**Operator**: _________________

This is the step-by-step runbook for migrating the **hub node** to v0.5.10. The hub is the PoA authority — all follower nodes sync from it. The hub must migrate first; followers re-sync afterwards.

> **Breaking change.** All nodes must run v0.5.10 code. A node still on v0.5.9 will reject fee=36 transactions and vice versa.

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
systemctl is-active aitbc-blockchain-node
systemctl is-active aitbc-agent-coordinator
systemctl is-active aitbc-wallet
systemctl is-active aitbc-bridge-monitor
# All should report "active"
```

- [ ] All services active

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

```bash
systemctl stop aitbc-bridge-monitor
systemctl stop aitbc-wallet
systemctl stop aitbc-agent-coordinator
systemctl stop aitbc-blockchain-node

# Verify all stopped
systemctl is-active aitbc-blockchain-node && echo "STILL RUNNING" || echo "stopped"
systemctl is-active aitbc-agent-coordinator && echo "STILL RUNNING" || echo "stopped"
systemctl is-active aitbc-wallet && echo "STILL RUNNING" || echo "stopped"
systemctl is-active aitbc-bridge-monitor && echo "STILL RUNNING" || echo "stopped"
```

- [ ] All 4 services stopped

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

```bash
systemctl start aitbc-blockchain-node
sleep 3
systemctl is-active aitbc-blockchain-node && echo "blockchain-node: active" || echo "blockchain-node: FAILED"

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
- [ ] agent-coordinator: active
- [ ] wallet: active
- [ ] bridge-monitor: active

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

Followers do **NOT** run the migration script. They re-sync from the hub.

```bash
# 1. Update code to v0.5.10 (git pull / deploy)
# 2. Stop all services
systemctl stop aitbc-bridge-monitor aitbc-wallet aitbc-agent-coordinator aitbc-blockchain-node

# 3. Flush Redis cache
redis-cli FLUSHDB

# 4. Restart with v0.5.10 code
systemctl start aitbc-blockchain-node aitbc-agent-coordinator aitbc-wallet aitbc-bridge-monitor

# 5. Verify sync from hub
curl -s http://localhost:8202/rpc/state/snapshot | python3 -m json.tool
# State root should match the hub's state root

# 6. Verify balances are scaled
curl -s http://localhost:8202/rpc/account/<your_address> | python3 -m json.tool
# Balance should be in seconds (large number)
```

---

## Rollback Procedure

If the migration fails or causes issues, roll back to pre-fork state:

```bash
# 1. Stop all services
systemctl stop aitbc-bridge-monitor aitbc-wallet aitbc-agent-coordinator aitbc-blockchain-node

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

# 5. Restart services
systemctl start aitbc-blockchain-node aitbc-agent-coordinator aitbc-wallet aitbc-bridge-monitor

# 6. Verify
curl -s http://localhost:8202/rpc/head | python3 -m json.tool
```

- [ ] Rollback tested in staging (recommended)

---

## Troubleshooting

### Migration script fails with "database is locked"

The blockchain node is still running or didn't shut down cleanly:
```bash
systemctl stop aitbc-blockchain-node
# Wait for clean shutdown
sleep 5
# Kill any lingering processes
pkill -f "aitbc_chain" || true
# Retry migration
```

### State root mismatch after restart

If the state root after restarting doesn't match the migration script output, the blockchain node may have recomputed it on startup. This is OK if the node is functional — the node's computed state root is authoritative. Verify by checking account balances are still scaled.

### Follower nodes can't sync

If followers report sync errors after the hub migrates:
1. Confirm follower is running v0.5.10 code (`grep "fee.*=.*36" apps/blockchain-node/src/aitbc_chain/rpc/transactions.py`)
2. Confirm follower flushed Redis (`redis-cli DBSIZE` → 0)
3. If still failing, follower may need to wipe local chain.db and re-sync from scratch:
   ```bash
   systemctl stop aitbc-blockchain-node
   mv /var/lib/aitbc/data/<chain_id>/chain.db /var/lib/aitbc/data/<chain_id>/chain.db.pre-fork.failed
   rm -f /var/lib/aitbc/data/<chain_id>/chain.db-wal /var/lib/aitbc/data/<chain_id>/chain.db-shm
   redis-cli FLUSHDB
   systemctl start aitbc-blockchain-node
   # Node will re-sync from hub
   ```

### Genesis.json has empty allocations

If `genesis.json` shows `"allocations": []` (as seen on some nodes), the genesis balances are stored in the `account` table, not in the genesis file. The migration script handles both cases — the `scale_genesis_json()` step will simply skip if allocations are empty, and the `scale_balances()` step handles the `account` table.

---

## Summary Checklist

| Step | Description | Done |
|------|-------------|------|
| P1 | Code deployed and verified | ☐ |
| P2 | Services running | ☐ |
| P3 | Database accessible | ☐ |
| P4 | Disk space sufficient | ☐ |
| P5 | Genesis file present | ☐ |
| P6 | Redis running | ☐ |
| P7 | Followers notified | ☐ |
| 1 | Announce start | ☐ |
| 2 | Stop all services | ☐ |
| 3 | Manual backup | ☐ |
| 4 | Run migration script | ☐ |
| 5 | Verify migration results | ☐ |
| 6 | Verify genesis.json | ☐ |
| 7 | Flush Redis | ☐ |
| 8 | Restart services | ☐ |
| 9 | Post-migration verification | ☐ |
| 10 | Test transaction | ☐ |
| 11 | Announce complete | ☐ |

---

## Sign-off

- **Migration performed by**: _________________
- **Date**: _________________
- **State root (post-migration)**: _________________
- **All checks passed**: ☐ Yes ☐ No (explain: _________________)
- **Followers notified**: ☐
