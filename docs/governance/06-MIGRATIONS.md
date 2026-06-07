# Database Migrations

## Overview

The Governance Service uses Alembic for database schema migrations. Migrations are versioned and can be applied, rolled back, and inspected.

## Prerequisites

- Python virtual environment activated
- Alembic installed (`pip install alembic`)
- Database configured (SQLite or PostgreSQL)

## Migration Directory

```
/opt/aitbc/apps/governance/alembic/
├── env.py              # Migration environment
├── script.py.mako      # Migration template
├── versions/           # Migration scripts
│   └── 001_initial_governance_schema.py
└── alembic.ini         # Alembic configuration
```

## Running Migrations

### Apply All Migrations

```bash
cd /opt/aitbc/apps/governance
/opt/aitbc/venv/bin/alembic upgrade head
```

### Apply Specific Migration

```bash
/opt/aitbc/venv/bin/alembic upgrade <revision>
```

### Check Current Version

```bash
/opt/aitbc/venv/bin/alembic current
```

### List All Migrations

```bash
/opt/aitbc/venv/bin/alembic history
```

### Rollback One Migration

```bash
/opt/aitbc/venv/bin/alembic downgrade -1
```

### Rollback to Specific Version

```bash
/opt/aitbc/venv/bin/alembic downgrade <revision>
```

## Migration 001: Initial Governance Schema

**Revision:** 001_initial_governance_schema
**Applied:** June 7, 2026

### Changes

**Tables Created:**
- governance_profiles
- proposals
- votes
- delegations
- governance_tokens
- token_stakes
- proposal_execution_log
- dao_treasury
- transparency_reports

**Indexes Created:**
- idx_proposals_status
- idx_proposals_voting_period
- idx_proposals_proposer
- idx_votes_proposal
- idx_votes_voter
- idx_votes_delegated
- idx_tokens_holder
- idx_tokens_voting_power
- idx_stakes_staker
- idx_stakes_unstakes_at
- idx_delegations_delegator
- idx_delegations_delegate
- idx_execution_log_proposal
- idx_execution_log_status

### Migration Script

Location: `/opt/aitbc/apps/governance/alembic/versions/001_initial_governance_schema.py`

## Creating New Migrations

### Generate Migration Script

```bash
cd /opt/aitbc/apps/governance
/opt/aitbc/venv/bin/alembic revision -m "description"
```

This creates a new migration script in `alembic/versions/`.

### Edit Migration Script

Edit the generated script to add your upgrade and downgrade logic:

```python
def upgrade() -> None:
    # Add your migration logic here
    pass

def downgrade() -> None:
    # Add rollback logic here
    pass
```

### Apply Migration

```bash
/opt/aitbc/venv/bin/alembic upgrade head
```

## Configuration

### alembic.ini

The Alembic configuration file is located at `/opt/aitbc/apps/governance/alembic.ini`.

**Key Settings:**
```ini
# Database URL (SQLite for development)
sqlalchemy.url = sqlite:////var/lib/aitbc/data/governance_service.db

# PostgreSQL for production (uncomment and configure)
# sqlalchemy.url = postgresql://aitbc_governance:password@localhost:5432/aitbc_governance
```

### env.py

The migration environment script is located at `/opt/aitbc/apps/governance/alembic/env.py`.

**Key Configuration:**
- Adds `src` directory to Python path for model imports
- Configures database engine from environment
- Sets up migration context

## Database Reset

### SQLite

```bash
# Delete existing database
rm /var/lib/aitbc/data/governance_service.db

# Re-run migrations
cd /opt/aitbc/apps/governance
/opt/aitbc/venv/bin/alembic upgrade head
```

### PostgreSQL

```bash
# Drop and recreate database
sudo -u postgres psql
DROP DATABASE aitbc_governance;
CREATE DATABASE aitbc_governance;
\q

# Re-run migrations
cd /opt/aitbc/apps/governance
/opt/aitbc/venv/bin/alembic upgrade head
```

## Troubleshooting

### Migration Fails with "Table already exists"

**Cause:** Database already has tables from previous migration or manual setup.

**Solution:**
```bash
# SQLite: Delete database file
rm /var/lib/aitbc/data/governance_service.db

# PostgreSQL: Drop and recreate database
sudo -u postgres psql -c "DROP DATABASE aitbc_governance;"
sudo -u postgres psql -c "CREATE DATABASE aitbc_governance;"
```

### ModuleNotFoundError

**Cause:** Python path not configured correctly in env.py.

**Solution:** Ensure `src` directory is added to sys.path in `alembic/env.py`:

```python
import sys
sys.path.insert(0, '/opt/aitbc/apps/governance/src')
```

### Database Connection Error

**Cause:** Incorrect database URL or credentials.

**Solution:** Check `alembic.ini` database URL and ensure database exists.

## Best Practices

1. **Always test migrations** on a development database first
2. **Write downgrade logic** for every migration
3. **Use descriptive migration messages** for history
4. **Review migration scripts** before applying to production
5. **Backup database** before running migrations in production
6. **Keep migrations reversible** when possible

## Migration History

```bash
/opt/aitbc/venv/bin/alembic history
```

Example output:
```
<base>  -> 001_initial_governance_schema (head), Initial governance schema
```

## References

- Alembic Documentation: https://alembic.sqlalchemy.org/
- SQLModel Documentation: https://sqlmodel.tiangolo.com/
