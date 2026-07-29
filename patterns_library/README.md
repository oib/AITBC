# AITBC Pattern Library

> **Copy-Paste Ready Code Patterns for Agent-Driven Development**

## Overview

This pattern library provides battle-tested, production-ready code patterns extracted from the AITBC codebase. Each pattern is:

- ✅ **Copy-Paste Ready** - Minimal customization needed
- ✅ **Security Validated** - RLS enforced, auth required, input validated
- ✅ **SOLID Compliant** - Follows architectural principles
- ✅ **Test Covered** - Includes testing patterns

## Stack applicability (ABS-257)

Every pattern declares which stack it assumes, in its markdown frontmatter:

```yaml
---
stack: [nextjs, clerk, prisma, postgres-rls]
---
```

**Taxonomy** (the closed vocabulary — extend it here, not ad hoc):

| Tag              | Means the pattern assumes…                                   |
| ---------------- | ------------------------------------------------------------ |
| `generic`        | nothing — language/framework-agnostic; **always applicable**  |
| `nextjs`         | Next.js App Router (`next/server`, route handlers)           |
| `react`          | React components (with shadcn/Radix)                         |
| `clerk`          | Clerk authentication                                         |
| `prisma`         | Prisma ORM                                                   |
| `postgres-rls`   | Postgres with Row Level Security policies                    |
| `stripe`         | Stripe payments                                              |
| `github-actions` | GitHub Actions CI                                            |
| `playwright`     | Playwright E2E tests                                         |

A project declares the stack it can actually use in its active profile
(`profiles/<name>/profile.yaml`):

```yaml
stack: [nextjs, react, clerk, prisma, postgres-rls, stripe, github-actions, playwright]
```

`scripts/pattern-applicability.sh` filters this library against that list, and the
`pattern-discovery` skill recommends **only** from its output — so a FastAPI/Firestore project
is never offered Next.js/Prisma/Clerk code:

```bash
scripts/pattern-applicability.sh         # applicable pattern paths for the active profile
scripts/pattern-applicability.sh --all   # every pattern with an APPLIES/EXCLUDED verdict
```

Rules:

- A pattern applies when it is tagged `generic`, or its tags intersect the profile's `stack:`.
- **No `stack:` key** in the profile → unfiltered, every pattern applies. Filtering is opt-in,
  so projects that predate this guard are unaffected.
- **`stack: []`** (empty, e.g. a FastAPI/Firestore project) → filtering is ON and only
  `generic` patterns apply. An empty list is a declaration, not a missing key.
- A profile name that **does not resolve** to a `profiles/<name>/` directory (typo, profile
  never committed) → the guard **fails closed** (ABS-269): only `generic` patterns are served
  and a `FAIL-CLOSED` warning names the profile and the searched path. A misconfiguration
  degrades to maximum protection, never to none. Fix it with `scripts/profile.sh set <name>`.
- An **untagged** pattern is treated as `generic`: the guard hides noise, it never hides a
  pattern nobody classified (your project's own patterns stay visible until you tag them).

## Pattern Index

### API Routes

| Pattern                                           | File                                     | Use Case                          |
| ------------------------------------------------- | ---------------------------------------- | --------------------------------- |
| [User Context API](./api/user-context-api.md)     | Basic authenticated API with RLS         | User-specific CRUD operations     |
| [Admin Context API](./api/admin-context-api.md)   | Admin-only API with elevated permissions | Admin dashboards, management      |
| [Webhook Handler](./api/webhook-handler.md)       | External webhook processing              | Stripe, Clerk, third-party events |
| [Zod Validation API](./api/zod-validation-api.md) | Input validation with Zod schemas        | Form submissions, API inputs      |

### UI Components

| Pattern                                              | File                           | Use Case                 |
| ---------------------------------------------------- | ------------------------------ | ------------------------ |
| [Authenticated Page](./ui/authenticated-page.md)     | Protected page with auth check | User dashboard, profile  |
| [Form with Validation](./ui/form-with-validation.md) | React Hook Form + Zod          | Data entry, settings     |
| [Data Table](./ui/data-table.md)                     | Server-side paginated table    | List views, admin panels |

### Database Operations

| Pattern                                                | File                           | Use Case             |
| ------------------------------------------------------ | ------------------------------ | -------------------- |
| [RLS Migration](./database/rls-migration.md)           | Add table with RLS policies    | New user data tables |
| [Prisma Transaction](./database/prisma-transaction.md) | Multi-step database operations | Complex workflows    |

### Testing

| Pattern                                                   | File                       | Use Case             |
| --------------------------------------------------------- | -------------------------- | -------------------- |
| [API Integration Test](./testing/api-integration-test.md) | Test API routes with RLS   | Endpoint validation  |
| [E2E User Flow](./testing/e2e-user-flow.md)               | Playwright end-to-end test | User journey testing |

### Security

| Pattern                                                       | File                              | Use Case                 |
| ------------------------------------------------------------- | --------------------------------- | ------------------------ |
| [Input Sanitization](./security/input-sanitization.md)        | XSS/injection prevention          | User input handling      |
| [Rate Limiting](./security/rate-limiting.md)                  | API rate limiting                  | Abuse prevention         |
| [Secrets Management](./security/secrets-management.md)        | Environment variable management   | Config security          |
| [RLS Validation](./security/rls-validation.md)                | RLS enforcement check (stub)      | Pre-deploy data-access review |
| [API Security Audit](./security/api-security-audit.md)        | API route security review (stub)  | Route audits             |
| [Vulnerability Scan](./security/vulnerability-scan.md)        | Dependency/secret scanning (stub) | Pre-release checks       |

### CI/CD

| Pattern                                                       | File                             | Use Case                 |
| ------------------------------------------------------------- | -------------------------------- | ------------------------ |
| [GitHub Actions Workflow](./ci/github-actions-workflow.md)     | Standard CI pipeline             | Automated quality gates  |
| [Deployment Pipeline](./ci/deployment-pipeline.md)             | Staging → production deployment  | Release management       |

### Configuration

| Pattern                                                       | File                             | Use Case                 |
| ------------------------------------------------------------- | -------------------------------- | ------------------------ |
| [Environment Config](./config/environment-config.md)           | Typed environment loading        | App configuration        |
| [Structured Logging](./config/structured-logging.md)           | JSON logging with correlation    | Observability            |

### Documentation

| Pattern                                                       | File                             | Use Case                 |
| ------------------------------------------------------------- | -------------------------------- | ------------------------ |
| [Feature Guide](./documentation/feature-guide.md)             | User-facing feature guide (stub) | New capability docs      |
| [API Reference](./documentation/api-reference.md)             | Endpoint reference docs (stub)   | API documentation        |
| [Migration Guide](./documentation/migration-guide.md)         | Breaking-change/upgrade guide (stub) | Migrations           |

## How to Use Patterns

### 1. Find the Right Pattern

Use the index above to find a pattern matching your use case.

### 2. Copy the Pattern

Each pattern file contains:

- **What It Does** - Purpose and use case
- **Code Pattern** - Copy-paste ready code
- **Customization Guide** - What to change
- **Security Checklist** - Validation points

### 3. Customize for Your Use Case

Follow the customization guide in each pattern:

- Replace placeholders (marked with `{...}`)
- Update type definitions
- Adjust business logic
- Run validation commands

### 4. Validate

Each pattern includes validation commands:

```bash
yarn lint && yarn type-check  # For all patterns
yarn test:integration          # For API patterns
yarn test:e2e                  # For UI patterns
```

## Pattern Discovery Protocol

**Before creating new patterns**, check:

1. **This library first** - Use existing patterns when possible
2. **Codebase search** - Look for similar implementations
3. **BSA/ARCHitect** - Propose new patterns for validation

## Pattern Creation Guidelines

When creating new patterns (BSA/ARCHitect only):

### Required Elements

- [ ] Clear use case description
- [ ] Complete, working code example
- [ ] Customization instructions with placeholders
- [ ] Security validation checklist
- [ ] Success validation commands

### Quality Standards

- [ ] RLS enforced (if database operations)
- [ ] Authentication required (if protected)
- [ ] Input validation with Zod
- [ ] Error handling comprehensive
- [ ] TypeScript strict mode compliant

### Documentation Format

```markdown
# Pattern Name

## What It Does

[Clear description of purpose and use case]

## When to Use

- Use case 1
- Use case 2

## Code Pattern

[Complete, copy-paste ready code]

## Customization Guide

1. Replace `{placeholder}` with your value
2. Update type definitions
3. Adjust business logic

## Security Checklist

- [ ] RLS context enforced
- [ ] Auth required
- [ ] Input validated

## Validation

[Commands to verify implementation]
```

## Contributing Patterns

**BSA/System Architect Only**:

1. Discover gap in pattern library
2. Extract pattern from proven implementation
3. Validate with System Architect
4. Document per template above
5. Add to this index

**Execution Agents**:

- Use existing patterns
- Report missing patterns to BSA
- Do NOT create new patterns

## Maintenance

- **Owner**: System Architect
- **Contributors**: BSA (pattern discovery and extraction)
- **Consumers**: All execution agents (FE, BE, QAS, etc.)
- **Update Frequency**: As new patterns emerge from production code

## Pattern Library Evolution

As patterns prove useful:

1. BSA identifies frequently implemented features
2. System Architect validates pattern
3. BSA extracts and documents pattern
4. Pattern added to library
5. Execution agents use pattern for future implementations

---

**Last Updated**: 2026-03
**Pattern Count**: 18
**Maintained by**: AITBC Development Team + System Architect
