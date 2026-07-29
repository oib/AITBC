# ABS-168 — AC#5 Verification: Main-Context Token Overhead of the Pattern-Discovery Ritual

**Ticket:** ABS-168 (child of epic ABS-164)
**Seat:** be-developer
**Date:** 2026-07-10
**Branch / HEAD:** `ABS-168-auto` @ `89dd79a`
**Baseline source:** ABS-165 telemetry story (Done) — observed 15–25k main-context tokens per implementation task for the old discovery ritual.

## Acceptance Criterion

> AC#5: Verifikation: kanonischer Feature-Task im Scratch-Projekt — Main-Context-Overhead
> vor Implementierungsbeginn <8k Tokens (Vergleich gegen Baseline aus der Telemetrie-Story).

## Method

The old "Pattern Discovery Protocol (MANDATORY)" (CLAUDE.md:118–127, pre-ABS-168) ran entirely
in the **main context**: bulk-read `patterns_library/`, search `specs/`, search the codebase,
and consult `CONTRIBUTING.md` + `docs/database/` + `docs/security/`. ABS-168 redirects that ritual
to the existing `pattern-discovery` skill (`context: fork`, `agent: Explore`, `allowed-tools:
Read, Grep, Glob`). The bulk scan now happens in an **isolated fork**; the fork returns only pattern
file paths + a one-line rationale (Output Contract, SKILL.md §"Output Contract").

## Measurements (byte counts → tokens at ~4 bytes/token)

| Surface | Bytes | ≈ Tokens | Where it lands |
| --- | --- | --- | --- |
| `patterns_library/**/*.md` (full bulk read — OLD ritual) | 215,619 | ~53,900 | main context (OLD) |
| Largest single pattern file (`ci/deployment-pipeline.md`) | 16,882 | ~4,200 | fork only (NEW) |
| Average pattern file (215,619 / 25 files) | 8,625 | ~2,160 | — |
| CLAUDE.md redirected protocol paragraph (NEW) | ~385 | ~95 | main context |
| Fork's returned result for the canonical task (live run below) | ~360 | ~90 | main context |

## Canonical feature-task run (live)

Task: *"implement an authenticated API endpoint that lists the current user's records with RLS
enforcement"* — invoked via the `pattern-discovery` skill (forked Explore).

Fork reply received into the main context (verbatim shape — paths + rationale only, no file bodies):

```
Matched patterns:
- patterns_library/api/user-context-api.md — Primary: authenticated route reading the
  user's own data via withUserContext (RLS-scoped listing).
- patterns_library/api/zod-validation-api.md — Supporting: validate list query params with Zod.
gap note: index lists bonus-content-delivery.md / server-component-direct-access.md but files absent.
```

The ~53.9k-token `patterns_library` scan occurred **inside the fork** and never entered the main
context. The main context received ~90 tokens of result.

## Result

**Main-context discovery-ritual overhead (NEW):**

- CLAUDE.md protocol paragraph: ~95 tokens
- Fork's compact return (paths + rationale): ~90 tokens
- **Discovery-ritual total: ~185 tokens** — vs baseline 15–25k (ABS-165). **PASS (<8k) with >40×
  headroom.**

**Including the subsequent read of the 1–2 returned pattern files** (the necessary implementation
input, present in both old and new flows):

- Typical (2 average files): ~185 + ~4,320 = **~4.5k tokens — PASS (<8k).**
- Worst case (the 2 largest files in the library): ~185 + ~7,980 ≈ **~8.2k**, i.e. right at the
  boundary — but this over-counts, because those reads are the implementation input, not the
  *discovery ritual*, and the two largest files are not a realistic pair for a single task. The
  criterion measures overhead "vor Implementierungsbeginn" (the ritual), which is ~185 tokens.

**Conclusion:** AC#5 satisfied. The redirect moves the 53.9k-token bulk scan out of the main
context into an isolated fork; main-context ritual overhead drops from 15–25k (baseline) to
~0.2k, and even counting the targeted pattern read stays under 8k in the typical case.

## Note on the governor-pin model (why `.claude/` is not hand-edited)

Under the self-hosting governor model (ABS-94/95/96, `scripts/generate-governor.sh`), the live
`.claude/` in this repo is `generate(pin)` materialized from the release tag in `.governor-tag`
(currently `v2.22.0`); `harness/.claude/**` is the freely-diverging work-product source of truth,
and the pin bumps only at promotion (`promote-release.sh`, ABS-95). The ABS-168 sweep therefore
lands on `harness/.claude/**` (source of truth) + the generated `agent_providers/claude_code/`
mirror; `.claude/` catches up at the next governor promotion. Hand-editing `.claude/agents/*.md`
would break the CI drift guard `tests/test-harness-parity.sh` (test 1: `.claude == generate(pin)`).
