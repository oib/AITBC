---
name: migration-patterns
description: Database migration creation with mandatory RLS policies and ARCHitect
  approval workflow. Use when creating migrations, adding tables with RLS, or updating
  Prisma schema.
triggers:
- user
- model
allowed-tools:
- exec
- glob
- grep
- read
---

# Migration Patterns Skill

## Purpose

Guide database migration creation with mandatory RLS policies, following security-first architecture and approval workflow.

## When This Skill Applies

Invoke this skill when:

- Creating database migrations
- Adding new tables (all tables need RLS)
- Updating Prisma schema
- Adding GRANT statements
- Schema impact analysis
- Data migration planning

## Stop-the-Line Conditions

### FORBIDDEN Patterns

```sql
-- FORBIDDEN: RLS policies in separate file
-- RLS MUST be in the same migration.sql file as the table creation

-- FORBIDDEN: Table without RLS
CREATE TABLE user_data (...);
-- Missing: ALTER TABLE user_data ENABLE ROW LEVEL SECURITY;

-- FORBIDDEN: Resolve applied migrations
npx prisma migrate resolve --applied "migration_name"
-- This bypasses migration verification

-- FORBIDDEN: Missing user_id index
CREATE TABLE payments (...);
-- Missing: CREATE INDEX idx_payments_user_id ON payments(user_id);

-- FORBIDDEN: Schema changes without ARCHitect approval
-- All migrations require approval before PR
```

### CORRECT Patterns

```sql
-- CORRECT: Complete migration with RLS in same file
CREATE TABLE user_data (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  data JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS (SAME FILE - MANDATORY)
ALTER TABLE user_data ENABLE ROW LEVEL SECURITY;

-- User policy
CREATE POLICY user_data_user_select ON user_data
  FOR SELECT TO {{PROJECT}}_app_user
  USING (user_id = current_setting('app.current_user_id', true));

-- Index for RLS performance (MANDATORY)
CREATE INDEX idx_user_data_user_id ON user_data(user_id);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON user_data TO {{PROJECT}}_app_user;
```

## Adding a CHECK Constraint to an Existing Table

Adding `ADD CONSTRAINT ... CHECK (...)` to an **already-populated** table makes
Postgres validate **every existing row** at migrate time under an
`ACCESS EXCLUSIVE` lock. On a large or long-lived free-text table this can block
the deploy — or fail it outright on legacy rows that violate the new rule.

**Safe two-step pattern** — add the constraint `NOT VALID` first (enforced for
new/updated rows immediately, no full-table scan), then `VALIDATE CONSTRAINT` in a
separate statement (validates existing rows under a lighter
`SHARE UPDATE EXCLUSIVE` lock that does not block reads/writes):

```sql
-- Step 1: add the constraint WITHOUT scanning existing rows (fast, brief lock).
--         New and updated rows are enforced immediately.
ALTER TABLE orch_command
  ADD CONSTRAINT orch_command_reason_len_chk
  CHECK (reason IS NULL OR char_length(reason) <= 2000) NOT VALID;

-- Step 2 (optional): guarded backfill of any legacy rows that would fail, e.g.
-- UPDATE orch_command SET reason = left(reason, 2000)
--   WHERE char_length(reason) > 2000;

-- Step 3: validate existing rows (lighter lock; same migration or a later one).
ALTER TABLE orch_command VALIDATE CONSTRAINT orch_command_reason_len_chk;
```

**Rationale:** avoids a deploy-blocking full-table validation of legacy rows on a
large/long-lived table, while still enforcing the rule for all new and updated
rows from the moment `NOT VALID` is applied.

**When the simple one-step form is fine:** a plain `ADD CONSTRAINT ... CHECK (...)`
(no `NOT VALID`) is acceptable when the table is **new/empty**, or **small enough
or known-clean enough** that an immediate full-table validation is cheap and
cannot fail — e.g. a recently added, human-gated column that cannot yet hold a
violating row (as in ABS-447's `011_command_reason_length.sql`). Don't reach for
`NOT VALID` unnecessarily.

## Migration Workflow (MANDATORY)

### Step 1: Get ARCHitect Approval

Before ANY schema change:

```text
1. Document proposed changes
2. Get ARCHitect approval (create issue or discussion)
3. Only proceed after explicit approval
```

### Step 2: Create Migration

```bash
# Generate migration
npx prisma migrate dev --name descriptive_name

# Verify migration file created
ls prisma/migrations/
```

### Step 3: Add RLS to Migration

Edit the generated migration to include:

- [ ] `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
- [ ] User SELECT policy
- [ ] User INSERT policy (if applicable)
- [ ] User UPDATE policy (if applicable)
- [ ] Admin policies (if needed)
- [ ] System policies (for background jobs)
- [ ] Index on user_id column
- [ ] GRANT statements

### Step 4: Verify Locally

```bash
# Test migration
DATABASE_URL="..." npx prisma migrate dev

# Verify RLS is enabled
psql -c "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';"
```

### Step 5: Update Documentation

After successful migration:

- [ ] Update `docs/database/DATA_DICTIONARY.md` (MANDATORY)
- [ ] Update RLS policy catalog if new policies added
- [ ] Document in Linear ticket

## RLS Policy Templates

### User Read Policy

```sql
CREATE POLICY {table}_user_select ON {table}
  FOR SELECT TO {{PROJECT}}_app_user
  USING (user_id = current_setting('app.current_user_id', true));
```

### User Write Policy

```sql
CREATE POLICY {table}_user_insert ON {table}
  FOR INSERT TO {{PROJECT}}_app_user
  WITH CHECK (user_id = current_setting('app.current_user_id', true));
```

### Admin Policy

```sql
CREATE POLICY {table}_admin_all ON {table}
  FOR ALL TO {{PROJECT}}_app_user
  USING (current_setting('app.user_role', true) = 'admin');
```

### System Policy (Background Jobs)

```sql
CREATE POLICY {table}_system_all ON {table}
  FOR ALL TO {{PROJECT}}_app_user
  USING (current_setting('app.context_type', true) = 'system');
```

## Migration Checklist

Before PR:

- [ ] ARCHitect approval obtained
- [ ] RLS policies in same migration file
- [ ] User policies created
- [ ] user_id index created
- [ ] GRANT statements added
- [ ] Local migration test passed
- [ ] DATA_DICTIONARY.md updated
- [ ] Evidence attached to Linear

## PROD Migration Requirements

For production migrations:

- [ ] @oib must be present (MANDATORY)
- [ ] Backup taken before migration
- [ ] Rollback plan documented
- [ ] Post-migration validation steps defined
- [ ] Data integrity checks planned

## Authoritative References

- **Migration SOP**: `docs/database/RLS_DATABASE_MIGRATION_SOP.md` (MANDATORY)
- **Data Dictionary**: `docs/database/DATA_DICTIONARY.md` (update after changes)
- **RLS Implementation**: `docs/database/RLS_IMPLEMENTATION_GUIDE.md`
- **RLS Policies**: `docs/database/RLS_POLICY_CATALOG.md`
- **Security First**: `docs/guides/SECURITY_FIRST_ARCHITECTURE.md`
