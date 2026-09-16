# Node Upgrades

**Last Updated:** 2026-09-16

Guide for upgrading a blockchain node.

There is no `aitbc-chain` package and no `pip install aitbc-chain` — the node
runs straight out of the `/opt/aitbc` git checkout with dependencies in
`/opt/aitbc/venv`. An upgrade is **git pull + systemctl restart**.

## Pre-Flight

```bash
cd /opt/aitbc
git fetch origin
git status --short                 # confirm the tree is clean
git log --oneline HEAD..origin/main | head -20   # what's coming in

# Record current chain state for comparison after the upgrade
aitbc blockchain height
aitbc blockchain status
```

If the pull touches `apps/blockchain-node/migrations/` (alembic), plan for a
schema migration — see *Database Migrations* below.

## Upgrade Order

Upgrade **followers first, hub last**. Followers only consume the chain; if a
release misbehaves you want it to fail where it can't halt block production.

1. Follower nodes (any order)
2. Hub / proposer node

## Upgrade Steps (per node)

```bash
# 1. Backup the chain database
aitbc blockchain backup --chain-id ait-hub.aitbc.bubuit.net \
  --path /backup --compress --verify

# 2. Pull the new code
cd /opt/aitbc
git pull                          # fast-forward to origin/main

# 3. Update dependencies if requirements/pyproject changed
source venv/bin/activate
pip install -r requirements.txt   # or: poetry install, per repo tooling

# 4. Apply DB migrations if the release ships them
#    (see Database Migrations — skip if none)
cd apps/blockchain-node && alembic upgrade head && cd /opt/aitbc

# 5. Restart services
systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
# hub additionally:
systemctl restart aitbc-blockchain-p2p

# 6. Watch startup
journalctl -u aitbc-blockchain-node -f
```

## Verify

```bash
# Height is advancing again
aitbc blockchain height
watch -n5 'aitbc blockchain height'

# On a follower: still subscribed and catching up
aitbc blockchain sync-status
journalctl -u aitbc-blockchain-node -f | grep -iE "subscri|heartbeat|bulk"

# RPC is healthy
curl -s http://localhost:8202/rpc/status
curl -s http://localhost:8202/health
```

Compare the post-upgrade height/head hash against the hub
(`curl -s https://hub.aitbc.bubuit.net/rpc/head`) — a restarted follower
should converge within a few bulk-sync passes; the hub should resume
producing at the `block_time_seconds` cadence.

## Database Migrations

Alembic migrations live in `apps/blockchain-node/migrations/` and are the
production migration path for `data/<chain_id>/chain.db`. When a release adds
a migration:

```bash
cd /opt/aitbc/apps/blockchain-node
/opt/aitbc/venv/bin/alembic upgrade head
```

Apply migrations **before** restarting `aitbc-blockchain-node`. On a
multi-node fleet, migrate the hub's database first (it is the schema
authority), then followers — or let a follower rebuild via bulk sync/export
if its DB is disposable.

## Rollback

```bash
cd /opt/aitbc
git log --oneline -5               # find the previous commit
git checkout <previous-sha>        # or: git reset --hard <sha>

# Roll back the schema if migrations ran (check migrations/versions for names)
cd apps/blockchain-node && alembic downgrade <previous-revision> && cd /opt/aitbc

systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
journalctl -u aitbc-blockchain-node -f
```

If the new code corrupted chain state, restore the pre-upgrade backup:

```bash
systemctl stop aitbc-blockchain-node aitbc-blockchain-rpc
aitbc blockchain restore --backup-file /backup/chain-YYYYMMDD.tar.gz --verify
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc
```

> Note: `git checkout <sha>` detaches HEAD — return to `main`
> (`git checkout main && git reset --hard origin/main` for the known-good ref)
> once the incident is over.

## Next

- [Node Quick Start](../getting-started/node-quickstart.md) — Get started
- [Operations](./3_operations.md) — Day-to-day ops
- [Monitoring](./7_monitoring.md) — Monitoring
