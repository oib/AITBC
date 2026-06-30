# v0.5.10 Hub Migration Overview

**Last Updated**: 2026-06-30
**Version**: 1.0

**Node**: `hub.aitbc.bubuit.net` (PoA authority)
**Chain ID**: `ait-hub.aitbc.bubuit.net`
**Date**: 2026-06-23

This is the step-by-step runbook for migrating the **hub node** to v0.5.10. The hub is the PoA authority — all follower nodes sync from it. The hub must migrate first; followers re-sync afterwards.

> **Breaking change.** All nodes must run v0.5.10 code. A node still on v0.5.9 will reject fee=36 transactions and vice versa.

> **Lessons learned.** This runbook was updated after the actual migration on 2026-06-23. Key findings:
> - **Hub has more services than expected** — `aitbc-blockchain-rpc` is a separate service from `aitbc-blockchain-node` and must be stopped/restarted too. See Step 2 and Step 8.
> - **Follower nodes must wipe chain.db** — flushing Redis alone is not enough. The local DB has stale pre-fork data and the node will think it's "up to date" by comparing against itself. See Follower Node Instructions.
> - **Follower `default_peer_rpc_url` must point to the hub** — if it points to `localhost`, the follower syncs from itself and never receives the migrated state. See Follower Node Instructions.
> - **Follower `aitbc-blockchain-rpc` must be restarted** — it caches DB connections and will return stale height/state root after chain.db is wiped. See Follower Node Instructions.
> - **State root from migration script differs from node's** — the script uses a simplified SHA-256 hash; the node uses its real MPT implementation. The node's state root is authoritative. See Troubleshooting.

## Documentation Structure

This migration runbook has been split into topic-focused files:

- **[Pre-flight Checks](./pre-flight-checks.md)** - Pre-migration verification (P1-P7)
- **[Migration Steps](./migration-steps.md)** - Step-by-step hub migration procedure (Step 1-8)
- **[Follower Instructions](./follower-instructions.md)** - Follower node migration procedures
- **[Troubleshooting](./troubleshooting.md)** - Common issues and solutions
- **[Rollback](./rollback.md)** - Rollback procedures if migration fails

## Quick Navigation

### Pre-flight Checks
- [P1. Code is deployed](./pre-flight-checks.md#p1-code-is-deployed)
- [P2. Services are currently running](./pre-flight-checks.md#p2-services-are-currently-running)
- [P3. Database is accessible and has data](./pre-flight-checks.md#p3-database-is-accessible-and-has-data)
- [P4. Disk space for backups](./pre-flight-checks.md#p4-disk-space-for-backups)
- [P5. Genesis file exists](./pre-flight-checks.md#p5-genesis-file-exists)
- [P6. Redis is running](./pre-flight-checks.md#p6-redis-is-running)
- [P7. Notify follower operators](./pre-flight-checks.md#p7-notify-follower-operators)

### Migration Steps
- [Step 1. Announce maintenance start](./migration-steps.md#step-1-announce-maintenance-start)
- [Step 2. Stop all services](./migration-steps.md#step-2-stop-all-services)
- [Step 3. Manual backup](./migration-steps.md#step-3-manual-backup-in-addition-to-script-backup)
- [Step 4. Run the migration script](./migration-steps.md#step-4-run-the-migration-script)
- [Step 5. Verify migration output](./migration-steps.md#step-5-verify-migration-output)
- [Step 6. Flush Redis](./migration-steps.md#step-6-flush-redis)
- [Step 7. Start services](./migration-steps.md#step-7-start-services)
- [Step 8. Verify post-migration state](./migration-steps.md#step-8-verify-post-migration-state)

### Related Topics
- [Follower Instructions](./follower-instructions.md) - Follower node procedures
- [Troubleshooting](./troubleshooting.md) - Common issues and solutions
- [Rollback](./rollback.md) - Rollback procedures

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.10 — Hub Migration Runbook
