# Database Adapter — Interface

Schema, migrations, and access control. Reversibility is the first design constraint;
destructive operations are human-approval territory.

## Operations

| Operation | Semantics |
|-----------|-----------|
| `plan_migration(change)` | Produce a forward + rollback migration pair. |
| `apply_migration(id)` | Apply against a target environment (never prod without human release). |
| `verify(fixtures)` | Validate a migration against realistic fixtures. |
| `check_access_control(change)` | Verify row/tenant isolation rules survive the change. |

## Providers

- **`supabase-postgres-rls`** (saw-stack) — backed by SAW's `rls-patterns` and
  `migration-patterns` skills, the `data-engineer` / `data-provisioning-eng` agents, and the
  mandatory [RLS Migration SOP](../../../docs/database/RLS_DATABASE_MIGRATION_SOP.md). Row-Level
  Security is enforced and checked as a gate.
- **`postgres`, `mysql`** — generic relational; access-control check maps to the engine's
  native mechanism.
- **`none`** — projects without a database (the capability and its gates are skipped).

## Invariants

- Every migration ships with a tested rollback or an explicit, human-visible irreversibility
  statement.
- Schema changes that break consumers are breaking changes — always human-gated.
- Destructive operations (drops, truncations, live backfills) require explicit human approval.
