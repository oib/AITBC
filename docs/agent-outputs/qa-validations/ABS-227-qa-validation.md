# QA Validation — ABS-227

**Date**: 2026-07-12  
**Actor**: qas  
**Branch**: ABS-227-auto  
**Commits**: 3423520 (scripts + tests), 5e4732c (agent-def + SOP + provider mirror), 72daca9 (ADR-A-0008 fix)  
**Working tree**: clean (git status --short empty)

---

## Test Suite Results (run this seat)

| Suite | Assertions | Result |
|---|---|---|
| `tests/test-migrate-project.sh` | 44/44 | PASS |
| `tests/test-changelog-slice.sh` | 18/18 | PASS |
| `tests/test-harness-parity.sh` | 6/6 | PASS |
| `shellcheck -S warning` (4 scripts) | — | exit 0 (clean) |

---

## AC Verification

### AC1 — E2E migration ≤10 LLM tool-calls ✅

Test section "AC1 + AC3: end-to-end migration (one driver invocation)": 22 PASSes cover a complete
v1→v2 fixture migration. Driver handles classify/hash/replace/branch/commit in one call.
Machine-readable stdout summary verified. By construction: 1 driver call + 1 report read + 1 write
summary ≈ 3 tool-calls.

### AC2 — Changelog slicer emits only from→to slice ✅

Multi-version jump 1.9.0→2.2.0 tested: includes v2.0.0, v2.1.0, v2.2.0; excludes the `--since`
version (exclusive lower bound) and older releases. Breaking-change extraction and migration_notes
verified. `--to` inclusive bound confirmed. Missing `--since` and missing file each exit 2. 18/18
PASS.

### AC3 — Conflict hunks pre-computed as diff -u in driver report ✅

Tests confirm: "report fences the conflict as a diff block" PASS, "report diff has a hunk header
(@@) — pre-computed diff -u" PASS, "diff shows the local (target) line" PASS, "diff shows the
incoming line" PASS. Seat reads only the report (verified in agent-def: driver ref at line 60–73,
no Bash reads of individual source/target files in the LLM procedure).

### AC4 — Missing ownership map → deterministic abort (exit 6) ✅

Four tests: "missing ownership map exits 6" PASS, "abort names the missing map" PASS, "abort states
no LLM fallback" PASS, "abort gives a handlungsanweisung" PASS.

### AC5 — Legacy abort cases unchanged ✅

All 10 abort-case tests PASS:
- exit 3: marker missing
- exit 4: version newer than source
- exit 5: dirty working tree
- exit 7: declared migration failure — marker NOT stamped, no commit created

### AC6 — Agent-def + SOP switched to driver; token before/after documented ✅

- `harness/claude/agents/boilerplate-migration.md`: 133 lines (slimmed from 216). Procedure prose
  replaced by driver invocation (`scripts/migrate-project.sh`) + LLM-only step at lines 60–93.
- `docs/sop/BOILERPLATE_MIGRATION_SOP.md`: v1.3 header present; driver route at §3 lines 18–25;
  exit-code table at §5; ADR-A-0008 special case named with `strip_acceptance_fields` /
  `copy_adr_preserving_frontmatter` at §3 line 112.
- Provider mirror: harness-parity 6/6 PASS confirms `agent_providers/claude_code` in sync.
- Token before/after: documented in BE gate-results comment (2026-07-12T09:07:38Z); table covers
  HARNESS_CHANGELOG.yml (full 1155 lines / ~25k tok → ~1.2k tok slice for 3-version jump, ~21×
  smaller), procedure re-execution (dozens of tool-calls → 0), drift-file full reads (→ diff -u
  hunks only).

---

## ADR-A-0008 Blocking Defect (Stage-1 Iteration 1) — Resolved ✅

Implementation in `scripts/migrate-project.sh`:
- `is_agentic_adr()` at L76: matches `adrs/agentic/ADR-*.md`
- `strip_acceptance_fields()` at L79: removes `status`, `accepted_by`, `accepted_date` from hash input
- `hash_adr_content_file()` at L88: uses `strip_acceptance_fields` for ADR hashing
- L255–256: baseline hash computed with acceptance fields stripped
- `copy_adr_preserving_frontmatter()` at L295: replaces upstream content, keeps project's acceptance frontmatter

Test coverage (7 assertions):
- "accepted ADR-A-0001 gets the upstream v2 content" PASS
- "ADR-A-0001 project acceptance status PRESERVED" PASS
- "ADR-A-0001 accepted_by PRESERVED" PASS
- "ADR-A-0001 accepted_date PRESERVED" PASS
- "accepted ADR (frontmatter-only change) is NOT a spurious conflict" PASS
- "ADR-A-0002 real body drift IS a conflict" PASS
- "drifted ADR-A-0002 body left untouched" PASS

---

## Non-Blocking Notes (Stage-1) — Addressed ✅

- L211 deletion-note comment: aligned to emit `MISSING_SRC_LIST` report note (confirmed by
  system-architect; folded in commit 72daca9).
- `.claude` generic-copy vs `sync-claude-harness.sh` overlap: resolved via up-front `DELEGATE_CLAUDE`
  guard (confirmed by system-architect; folded in commit 72daca9).

---

## Verdict

**APPROVED**. AC1–AC6 satisfied. ADR-A-0009 (zero-dep bash), ADR-A-0008 (ownership model), ADR-A-0010
(minimal change) all respected. 44+18+6 = 68 assertions PASS, 0 FAIL. Shellcheck clean.
