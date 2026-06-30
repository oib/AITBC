# v0.5.10 Hub Migration — Pre-flight Checks

**Last Updated**: 2026-06-30
**Version**: 1.0

Complete these **before** the maintenance window. All items must pass.

## P1. Code is deployed

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

## P2. Services are currently running

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

## P3. Database is accessible and has data

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

## P4. Disk space for backups

```bash
# Need at least 2x chain.db size for backups
CHAIN_DB=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db
df -h "$(dirname "$CHAIN_DB")"
du -sh "$CHAIN_DB"
```

- [ ] Sufficient disk space (≥ 2× chain.db size free)

## P5. Genesis file exists

```bash
GENESIS=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/genesis.json
cat "$GENESIS" | python3 -m json.tool
```

- [ ] genesis.json present and valid JSON

## P6. Redis is running

```bash
redis-cli ping
# Expected: PONG
```

- [ ] Redis responding

## P7. Notify follower operators

All follower node operators must be notified of the fork time. Followers do NOT run the migration script — they update code, flush Redis, and re-sync from the hub.

- [ ] Follower operators notified of fork time: _________________

## Related Topics

- [Overview](./overview.md) - Migration overview and documentation structure
- [Migration Steps](./migration-steps.md) - Step-by-step migration procedure

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.10 — Hub Migration Runbook
