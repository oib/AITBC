# Gate the stack-specific `security-audit` skill, or split it by stack

- **Date**: 2026-07-29
- **Source**: AITBC-60 epic retro (dependency/security audit remediation)
- **Boilerplate version in use**: 2.35.0
- **Boilerplate-owned files**: `.claude/skills/security-audit/SKILL.md`
  (harness source: `harness/claude/skills/security-audit/`)

## Rationale

The shipped `security-audit` skill advertises itself stack-agnostically in its frontmatter:

```yaml
name: security-audit
description: RLS validation, security audits, OWASP compliance, and vulnerability scanning.
             Use when validating RLS policies, auditing API routes, or scanning for security issues.
```

The trailing clause — *"or scanning for security issues"* — matches any security work in any
project. The body, however, is exclusively TypeScript/Prisma/Next.js/Supabase-RLS:

| Measure | `.claude/skills/security-audit/SKILL.md` |
| ------- | ---------------------------------------- |
| Total lines | 207 |
| `typescript` code blocks | 2 |
| `python` code blocks | 0 |
| Mentions of Prisma / RLS / Supabase / Next.js | 23 |
| Mentions of bandit / pip-audit / FastAPI / SQLModel / Poetry | 0 |

AITBC is a Python 3.13 / FastAPI / SQLModel / Poetry monorepo with no Prisma, no Supabase and
no Next.js. In this repo the skill is not merely inert — its normative sections assert
concrete rules with no referent here:

- *FORBIDDEN*: "Direct Prisma calls (bypass RLS)", `prisma.user.findMany()`
- *CORRECT*: "RLS context wrapper", `withUserContext(prisma, userId, ...)`

An agent that loads this skill on a Python security task receives confident, specific, and
wholly inapplicable guidance. An absent skill leaves a gap the agent can notice. This one answers instead.

### Observed evidence

Epic AITBC-60 ran 9 security stories (AITBC-51..59): 4 CVE remediations (ecdsa, msgpack,
pydantic-settings, starlette) and 5 bandit rule-category triage passes (B608, B108, B104,
B310, B113) covering 107 findings. This is squarely the skill's advertised trigger surface —
"vulnerability scanning", "pre-deployment security review", "SQL injection". The skill
contributed nothing to any of the 9, because the procedures the work actually required
(bandit triage with `# nosec` justification, `pip-audit` remediation with lockfile bump and
re-scan) do not appear anywhere in it.

## Suggested boilerplate change

One of the following, in increasing order of effort:

1. **Narrow the frontmatter `description`** so the skill stops matching non-TS projects.
   Drop the stack-agnostic tail ("or scanning for security issues") and name the stack
   explicitly: *"...for Next.js/Prisma/Supabase projects."* One-line change; removes the
   mis-fire without touching content.
2. **Rename to match the content** — `security-audit-prisma-rls` (or similar) — so both the
   name and description carry the stack. Discoverability then matches applicability.
3. **Split by stack** — `security-audit/` becomes a thin stack-agnostic core (OWASP checklist,
   secret-exposure scan, auth-on-route review) with stack-specific companions layered under
   it. Most work, but it is the only option that gives Python consumers something usable.

Options 1 and 2 are strictly cleanups of an over-broad trigger and are worth doing regardless
of whether 3 is ever taken on.

If the harness edit is made, note that `agent_providers/claude_code/` is a generated mirror of
`harness/claude/skills/` and must be regenerated in the same commit
(`bash scripts/generate-governor.sh --providers`).

## Impact

- **Who benefits**: every consumer project not on the TS/Prisma/Supabase stack. The skill
  loads on a matching description and then misleads.
- **Risk**: option 1/2 near-zero (metadata only). Option 3 is a content project.
- **Effort**: option 1 ~1 line; option 2 a rename plus mirror regeneration; option 3 substantial.
- **Note**: this is a *trigger-scoping* defect, not a quality complaint about the skill's
  content, which is presumably correct for the stack it was written for.

## Copy-paste-ready issue body

```markdown
**Title**: `security-audit` skill advertises stack-agnostically but is TS/Prisma/RLS-only

**Finding**

`.claude/skills/security-audit/SKILL.md` (harness source `harness/claude/skills/security-audit/`)
has a frontmatter description ending "...or scanning for security issues", which matches
security work in any project. Its body is exclusively TypeScript/Prisma/Next.js/Supabase-RLS:

- 207 lines total; 2 `typescript` code blocks, 0 `python`
- 23 mentions of Prisma/RLS/Supabase/Next.js; 0 of bandit/pip-audit/FastAPI/SQLModel/Poetry
- Normative sections assert stack-specific rules with no referent off-stack, e.g.
  FORBIDDEN `prisma.user.findMany()`, CORRECT `withUserContext(prisma, userId, ...)`

On a Python/FastAPI consumer project the skill loads on its broad description and then supplies
confident, specific, inapplicable guidance. An absent skill leaves a gap the agent can notice; this one answers instead.

**Repro**

1. Adopt the boilerplate in a non-TS project (here: Python 3.13 / FastAPI / SQLModel / Poetry).
2. Run any security task matching "vulnerability scanning" or "pre-deployment security review".
3. The `security-audit` skill matches on description; its content addresses a stack the project
   does not use.

Live occurrence: consumer project on v2.35.0, 2026-07-29. A 9-story security epic (4 CVE
remediations + 5 bandit rule-category triage passes, 107 findings) ran entirely within the
skill's advertised trigger surface and drew nothing from it — the procedures the work needed
(bandit triage with `# nosec` justification; `pip-audit` remediation with lockfile bump and
re-scan) appear nowhere in the skill.

**Fix**

Any of, increasing effort:

1. Narrow the frontmatter `description`: drop the stack-agnostic tail and name the stack
   ("...for Next.js/Prisma/Supabase projects"). One line; stops the mis-fire.
2. Rename to `security-audit-prisma-rls` so name and description both carry the stack.
3. Split into a stack-agnostic core (OWASP checklist, secret-exposure scan, auth-on-route
   review) plus stack-specific companions — the only option that leaves non-TS consumers with
   something usable.

(1)/(2) are worth doing independently of (3). If `harness/claude/skills/` is edited, regenerate
the `agent_providers/claude_code/` mirror in the same commit
(`bash scripts/generate-governor.sh --providers`).

**Fork**

No local fork. Reported upstream from the consumer project; the boilerplate-owned skill file was
not modified locally (ADR-A-0008).
```
