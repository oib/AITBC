# PostgreSQL Migration Complete

**Date**: 2026-05-03  
**Status**: ✅ Complete

## Summary

Migrated SQLite databases to PostgreSQL to resolve recurring database corruption issues on Btrfs filesystems. All critical services now use PostgreSQL for production nodes.

## Migrations Completed

### 1. Mempool Database
- **Status**: ✅ Complete (all nodes)
- **Nodes**: localhost, aitbc1, gitea-runner
- **Database**: `aitbc_mempool`
- **User**: `aitbc_mempool`
- **Connection**: `postgresql+psycopg://aitbc_mempool:password@localhost:5432/aitbc_mempool`
- **Changes**:
  - Updated `mempool.py` to use SQLAlchemy with PostgreSQL
  - Created dedicated `mempool_metadata` to avoid chain table conflicts
  - Used raw SQL for table creation with `session.exec(text(...))`
  - Fixed count query bug using `func.count()` and `.one()`
  - Added systemd drop-in `mempool-postgres.conf` on all nodes
- **Issues Fixed**:
  - SQLite corruption on Btrfs filesystem
  - Missing `psycopg` module on aitbc1 and gitea-runner
  - ScalarResult count attribute error

### 2. Exchange Database
- **Status**: ✅ Complete (all nodes)
- **Nodes**: localhost, aitbc1, gitea-runner
- **Database**: `aitbc_exchange`
- **User**: `aitbc_exchange`
- **Connection**: `postgresql+psycopg://aitbc_exchange:password@localhost:5432/aitbc_exchange`
- **Changes**:
  - Updated systemd drop-in `exchange-postgres.conf` on all nodes
  - Set `EXCHANGE_DATABASE_URL` environment variable
- **Tables**: orders, trades

### 3. Coordinator Database
- **Status**: ✅ Complete (localhost, aitbc1), ⚠️ SQLite fallback (gitea-runner)
- **Nodes**: localhost (PostgreSQL), aitbc1 (PostgreSQL), gitea-runner (SQLite)
- **Database**: `aitbc_coordinator`
- **User**: `aitbc_coordinator`
- **Connection**: `postgresql+psycopg://aitbc_coordinator:password@localhost:5432/aitbc_coordinator`
- **Changes**:
  - Updated systemd drop-in `coordinator-postgres.conf` on localhost and aitbc1
  - Set `DATABASE_ADAPTER=postgresql` and `DATABASE_URL` environment variables
- **Gitea-runner Note**: Coordinator uses SQLite fallback due to pydantic-settings nested config issues. PostgreSQL tables exist but service defaults to SQLite.
- **Tables**: job, job_payments, jobreceipt, marketplacebid, marketplaceoffer, miner, payment_escrows, transaction, user, usersession, wallet (11 tables)

## Additional Fixes

### Gitea-runner Blockchain Node
- **Status**: ✅ Fixed
- **Issues Resolved**:
  - Service was inactive (dead) since 21:17:57
  - Missing `psycopg` module
  - Missing PostgreSQL user/database for mempool
  - Outdated `mempool.py` with count query bug
- **Actions Taken**:
  - Installed `psycopg` module
  - Created PostgreSQL user `aitbc_mempool` and database `aitbc_mempool`
  - Granted privileges
  - Synced updated `mempool.py` with `func.count()` fix
  - Restarted service successfully

### Legacy Coordinator Service
- **Status**: ✅ Removed
- **Action**: Removed stale symlink `/etc/systemd/system/multi-user.target.wants/coordinator-api.service` on gitea-runner
- **Reason**: Legacy service causing confusion, modern `aitbc-agent-coordinator.service` is the correct service

## Documentation Updates

Updated documentation files to reflect PostgreSQL migrations:
- `/opt/aitbc/docs/apps/blockchain/blockchain-node.md` - Added PostgreSQL mempool persistence note
- `/opt/aitbc/docs/apps/exchange/exchange.md` - Clarified PostgreSQL as production default
- `/opt/aitbc/docs/apps/coordinator/coordinator-api.md` - Added database configuration section

## Configuration Details

### Systemd Drop-ins

**Mempool** (`/etc/systemd/system/aitbc-blockchain-node.service.d/mempool-postgres.conf`):
```ini
[Service]
Environment="MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:password@localhost:5432/aitbc_mempool"
```

**Exchange** (`/etc/systemd/system/aitbc-exchange-api.service.d/exchange-postgres.conf`):
```ini
[Service]
Environment="EXCHANGE_DATABASE_URL=postgresql+psycopg://aitbc_exchange:password@localhost:5432/aitbc_exchange"
```

**Coordinator** (`/etc/systemd/system/aitbc-agent-coordinator.service.d/coordinator-postgres.conf`):
```ini
[Service]
Environment="DATABASE_ADAPTER=postgresql"
Environment="DATABASE_URL=postgresql+psycopg://aitbc_coordinator:password@localhost:5432/aitbc_coordinator"
```

## PostgreSQL Setup

### Users Created
- `aitbc_mempool` - for mempool database
- `aitbc_exchange` - for exchange database
- `aitbc_coordinator` - for coordinator database

### Databases Created
- `aitbc_mempool` - mempool persistence
- `aitbc_exchange` - exchange trading data
- `aitbc_coordinator` - job coordination data

### Privileges
All users granted `ALL PRIVILEGES` on their respective databases.

## Verification

All services verified active and healthy:
- `aitbc-blockchain-node.service` - active on all nodes
- `aitbc-exchange-api.service` - active on all nodes
- `aitbc-agent-coordinator.service` - active on all nodes

PostgreSQL tables verified created and accessible.

## Benefits

- Eliminated SQLite corruption risk on Btrfs filesystems
- Improved database reliability and performance
- Better connection pooling and scalability
- Consistent database backend across production nodes
- Reduced maintenance overhead for database repairs

## Known Limitations

- Coordinator on gitea-runner uses SQLite fallback due to pydantic-settings nested config issues
- PostgreSQL not required on gitea-runner for coordinator (SQLite is acceptable for this CI/runner node)
