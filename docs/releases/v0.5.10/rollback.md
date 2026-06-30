# v0.5.10 Hub Migration — Rollback Procedure

**Last Updated**: 2026-06-30
**Version**: 1.0

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

## Related Topics

- [Overview](./overview.md) - Migration overview
- [Migration Steps](./migration-steps.md) - Hub migration procedure
- [Troubleshooting](./troubleshooting.md) - Common issues and solutions

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.10 — Hub Migration Runbook
