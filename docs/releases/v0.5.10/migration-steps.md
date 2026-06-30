# v0.5.10 Hub Migration — Migration Steps

**Last Updated**: 2026-06-30
**Version**: 1.0

Execute these in order during the maintenance window. Do not skip steps.

## Step 1. Announce maintenance start

```bash
echo "[$(date -u)] v0.5.10 hub migration STARTED" | tee -a /var/log/aitbc-migration.log
```

- [ ] Logged

## Step 2. Stop all services

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

## Step 3. Manual backup (in addition to script backup)

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

## Step 4. Run the migration script

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

## Step 5. Verify migration results

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

## Step 6. Verify genesis.json was scaled

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

## Step 7. Flush Redis cache

```bash
redis-cli FLUSHDB
# Expected: OK

# Verify cache is empty
redis-cli DBSIZE
# Expected: 0
```

- [ ] Redis flushed
- [ ] Cache size is 0

## Step 8. Restart services

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

## Step 9. Post-migration verification

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

## Step 10. Test a transaction (optional but recommended)

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

## Step 11. Announce migration complete

```bash
echo "[$(date -u)] v0.5.10 hub migration COMPLETED. State root: $(curl -s http://localhost:8202/rpc/state/snapshot | python3 -c 'import sys,json; print(json.load(sys.stdin).get("state_root","unknown"))')" | tee -a /var/log/aitbc-migration.log
```

- [ ] Completion logged
- [ ] Follower operators notified to proceed with their steps

## Related Topics

- [Overview](./overview.md) - Migration overview
- [Pre-flight Checks](./pre-flight-checks.md) - Pre-migration verification
- [Follower Instructions](./follower-instructions.md) - Follower node procedures
- [Troubleshooting](./troubleshooting.md) - Common issues and solutions
- [Rollback](./rollback.md) - Rollback procedures

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.10 — Hub Migration Runbook
