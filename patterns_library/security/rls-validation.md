---
stack: [prisma, postgres-rls]
---

# RLS Enforcement Validation Pattern

> **Status: stub.** Minimal placeholder so agent/skill references resolve
> (ABS-147). Flesh out from the live implementation when this pattern is next
> exercised.

## What It Does

Validates that every database access path enforces Row Level Security: user
isolation holds, admin access is scoped, and system-context operations are
audited. Complements the `security-audit` skill.

## When to Use

- Before deploying any feature that touches user-owned data
- When reviewing new API routes or Prisma queries for RLS context helpers
  (`withUserContext`, `withAdminContext`, `withSystemContext`)

## See Also

- Skill: `security-audit`
- `docs/database/RLS_IMPLEMENTATION_GUIDE.md`
- `patterns_library/database/rls-migration.md`
