# Node Upgrades
Guide for upgrading your blockchain node.

## Upgrade Process

### Check Current Version

```bash
aitbc-chain version
```

### Check for Updates

```bash
aitbc-chain check-update
```

### Upgrade Steps

```bash
# 1. Backup data
aitbc-chain backup --output /backup/chain-$(date +%Y%m%d).tar.gz

# 2. Stop node gracefully
aitbc-chain stop

# 3. Upgrade software
pip install --upgrade aitbc-chain

# 4. Review migration notes
cat CHANGELOG.md

# 5. Start node
aitbc-chain start
```

## Version-Specific Upgrades

### v0.1.0 → v0.2.0

```bash
# Database migration required
aitbc-chain migrate --from v0.1.0
```

### v0.2.0 → v0.3.0

```bash
# Configuration changes
aitbc-chain migrate-config --from v0.2.0
```

## Rollback Procedure

```bash
# If issues occur, rollback
pip install aitbc-chain==0.1.0

# Restore from backup
aitbc-chain restore --input /backup/chain-YYYYMMDD.tar.gz

# Start old version
aitbc-chain start
```

## Upgrade Notifications

```bash
# Enable upgrade alerts
aitbc-chain alert --metric upgrade_available --action notify
```

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Operations](./3_operations.md) — Day-to-day ops
- [Monitoring](./7_monitoring.md) — Monitoring
