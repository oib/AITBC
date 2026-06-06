# Coordinator API Migrations

Database migration scripts for the Coordinator API.

## Files

| File | Description |
|------|-------------|
| `001_initial_schema.sql` | Initial database schema (tables) |
| `002_indexes.sql` | Performance indexes |
| `003_data_migration.py` | Data migration utilities |

## Running Migrations

### Prerequisites

- PostgreSQL 14+
- Python 3.10+ (for data migrations)
- `asyncpg` package

### Apply Schema

```bash
# Connect to database
psql -h localhost -U aitbc -d coordinator

# Run migrations in order
\i 001_initial_schema.sql
\i 002_indexes.sql
```

### Run Data Migrations

```bash
# Install dependencies
pip install asyncpg

# Backfill job history
python 003_data_migration.py --action=backfill_history

# Update miner statistics
python 003_data_migration.py --action=update_stats

# Run all maintenance tasks
python 003_data_migration.py --action=all

# Migrate from SQLite
python 003_data_migration.py --action=migrate_jobs --input-file=/path/to/jobs.db

# Migrate receipts from JSON
python 003_data_migration.py --action=migrate_receipts --input-file=/path/to/receipts.json
```

## Schema Overview

### Tables

- **jobs** - AI compute jobs
- **miners** - Registered GPU miners
- **receipts** - Cryptographic receipts
- **blocks** - Blockchain blocks
- **transactions** - On-chain transactions
- **api_keys** - API authentication
- **job_history** - Event history for analytics

### Key Indexes

- `idx_jobs_pending` - Fast pending job lookup
- `idx_miners_available` - Available miner selection
- `idx_receipts_provider_created` - Miner receipt history
- `idx_receipts_client_created` - Client receipt history

## Rollback

To rollback migrations:

```sql
-- Drop all tables (DESTRUCTIVE)
DROP TABLE IF EXISTS job_history CASCADE;
DROP TABLE IF EXISTS api_keys CASCADE;
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS blocks CASCADE;
DROP TABLE IF EXISTS receipts CASCADE;
DROP TABLE IF EXISTS miners CASCADE;
DROP TABLE IF EXISTS jobs CASCADE;
```
