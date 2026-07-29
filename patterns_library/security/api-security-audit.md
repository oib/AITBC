---
stack: [generic]
---

# API Security Audit Pattern

> **Status: stub.** Minimal placeholder so agent/skill references resolve
> (ABS-147). Flesh out from the live implementation when this pattern is next
> exercised.

## What It Does

Structured review of an API route: authentication present, RLS context enforced,
input validated (Zod), and errors handled without leaking internals.

## When to Use

- Reviewing new or changed API routes before merge
- Periodic security sweeps of the route surface

## See Also

- Skill: `security-audit`
- `patterns_library/api/zod-validation-api.md`
- `patterns_library/security/input-sanitization.md`
