# Pattern-Discovery Skill: Fork-Based Pattern Lookup

**Shipped in**: ABS-168 (child of epic ABS-164)
**Effective from**: harness v2.23.0 (next governor promotion)

---

## What Changed

Before ABS-168, the mandatory Pattern Discovery Protocol required every implementing agent to
bulk-read `patterns_library/` (211 KB, ~53k tokens), search `specs/`, search the codebase, and
consult `CONTRIBUTING.md`, `docs/database/`, and `docs/security/` — all in the main context.
The `pattern-discovery` skill already existed with `context: fork` but nothing pointed agents to use it.

ABS-168 makes the skill the sole entry point:

| Surface | Before | After |
|---|---|---|
| CLAUDE.md §"Pattern Discovery Protocol" | 5-step bulk-read list | One-line skill invocation |
| 8 agent defs (bsa, be-developer, fe-developer, qas, security-engineer, data-engineer, tech-writer) | `cat/ls patterns_library/…` blocks | Skill invocation reference |
| `harness/.claude/skills/pattern-discovery/SKILL.md` | No output contract | Explicit Output Contract section |
| Main-context discovery overhead | ~32k tokens (partial) to ~54k (full) | ~200 tokens (fork reply only) |

---

## How the Skill Works

Invoke it before any feature implementation:

```
/pattern-discovery [task description]
```

The skill runs as an isolated Explore fork (`context: fork`, `agent: Explore`, `allowed-tools: Read, Grep, Glob`). The fork scans `patterns_library/` internally and returns a compact result into the main context.

### Output Contract

The fork reply contains exactly:

1. The matched pattern file path(s) — at most 2, e.g. `patterns_library/api/user-context-api.md`
2. One line of rationale per path (why this pattern matches the task)
3. Optionally, a one-line gap note when no pattern matches (`gap: <missing pattern> — report to BSA`)

The fork **never** echoes file bodies, code blocks, or directory listings. After receiving the reply, the caller reads just the 1–2 returned files in the main context.

### Example

Task: *implement an authenticated API endpoint that lists the current user's records with RLS enforcement*

Fork reply:

```
Matched patterns:
- patterns_library/api/user-context-api.md — Primary: authenticated route reading the
  user's own data via withUserContext (RLS-scoped listing).
- patterns_library/api/zod-validation-api.md — Supporting: validate list query params with Zod.
```

The main context receives ~200 tokens. The ~53.9k-token scan ran inside the fork and never entered the main context.

---

## Token Impact (AC#5 Verification)

Measured against the ABS-165 telemetry baseline:

| Scenario | Tokens |
|---|---|
| OLD: partial bulk-read (typical agent behavior, ~5 files) | ~15,000–25,000 |
| OLD: full `patterns_library/` bulk-read | ~53,900 |
| NEW: fork reply (2 paths + rationale) | ~200 |
| NEW: fork reply + reading 2 average pattern files | ~4,500 |
| AC#5 threshold | <8,000 |

**Result**: canonical feature-task overhead drops from ~32k tokens to ~4,515 tokens — an 88% reduction. See `docs/agent-outputs/ABS-168-ac5-token-overhead-verification.md` for the full measurement.

---

## Why `.claude/` Was Not Hand-Edited

The live `.claude/` directory in this repo is generated output — `generate(pin)` materialized
from the release tag in `.governor-tag` (currently `v2.22.0`, per ABS-94/ABS-95). The
authoritative source of truth is `harness/.claude/`. ABS-168 changes land in
`harness/.claude/agents/` and `harness/.claude/skills/pattern-discovery/SKILL.md`; the live
`.claude/` catches up at the next governor promotion (`promote-release.sh`). Hand-editing
`.claude/agents/` would break `tests/test-harness-parity.sh` (test 1: `.claude == generate(pin)`).

---

## Pattern Coverage

After the fork returns a path, the caller reads only that file. The full library covers:

| Category | Available patterns |
|---|---|
| API | `user-context-api.md`, `admin-context-api.md`, `webhook-handler.md`, `zod-validation-api.md`, `bonus-content-delivery.md` |
| UI | `authenticated-page.md`, `form-with-validation.md`, `data-table.md`, `marketing-page.md` |
| Database | `rls-migration.md`, `prisma-transaction.md`, `server-component-direct-access.md` |
| Testing | `api-integration-test.md`, `e2e-user-flow.md` |
| Security | `input-sanitization.md`, `rate-limiting.md`, `secrets-management.md` |
| CI | `github-actions-workflow.md`, `deployment-pipeline.md` |
| Config | `environment-config.md`, `structured-logging.md` |

If the fork returns a gap note, report it to the BSA for future pattern extraction.

---

## Scope of the Agent-Def Sweep

AC#3 covered all 18 agent definitions in `harness/.claude/agents/` and their provider mirror in `agent_providers/claude_code/prompts/`:

- **8 defs changed**: bsa, be-developer, fe-developer, qas, security-engineer, data-engineer, tech-writer, (system-architect was already redirected on the epic branch before this story)
- **2 defs unchanged** (conceptual mentions only, no read commands): issue-enrichment, ui-ux-design
- **Augment provider** (`agent_providers/augment/`): outside declared scope; follow-up story planned

Zero residual `cat patterns_library` or `ls patterns_library` commands remain in any of the 18 harness agent definitions.

---

## Governance References

- `harness/.claude/skills/pattern-discovery/SKILL.md` — skill definition and Output Contract
- `adrs/agentic/ADR-A-0003-context-minimization.md` — context minimization as a workflow quality requirement
- `adrs/agentic/ADR-A-0013-self-hosting-stable-governs-dev.md` — governor-pin model
- `docs/agent-outputs/ABS-168-ac5-token-overhead-verification.md` — token measurement evidence
- `docs/agent-outputs/qa-validations/ABS-168-qa-validation.md` — QAS validation report
