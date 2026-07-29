# QA Validation Report — ABS-147

**Ticket**: ABS-147 — Reference reconciliation: broken links, missing spec/pattern targets, docs/adr path, status-count + assign op docs
**QAS Actor**: qas
**Date**: 2026-07-08
**Commits under review**: `a52a79d`, `3eada78`, `a33b74f` (HEAD)
**Verdict**: ✅ **APPROVED — Approved for RTE**

---

## Validation Approach

Reference-reconciliation ticket (docs + shipped harness config; no application code). Validation performed by independent existence-checking every enumerated finding against the live repo, running the harness parity suite independently, verifying pre-release-check environmental failures, and conducting a relative-link sweep over all 23 touched files.

---

## AC1 — Every listed link/reference resolves or is removed ✅

### Broken links / phantom targets

| Finding | Claim | QAS Verified |
|---------|-------|--------------|
| `docs/whitepapers/README.md` phantom MODERNIZATION-444 "Document #1" | Removed; docs renumbered 1–4 | ✅ Confirmed — no MODERNIZATION-444 reference; 4-doc structure present |
| Date-scope disclaimer on whitepapers | Added one-liner | ✅ Line 5: "These whitepapers are 2026-03 snapshots…" |
| `KT-META-PROMPT.md:461` `-444` file ref | Removed as file ref; explanatory note retained | ✅ Lines 1,6 carry epic-identity context only; line 34 explicit note that whitepaper "was never part of this repository" |
| `AGENT-PERSPECTIVE.md` `-444` references | Removed | ✅ `grep -n "444"` → no output |
| `DRAFT-workflow-v2-sim-results.md:3` → deleted spec | Repointed to `specs/ABS-69-workflow-v3-full-agent-team-spec.md` | ✅ Target exists; repoint verified |
| `harness/.claude/README.md:167,387` → `workflow-analysis/HARNESS_AND_SKILLS_AUDIT` | Removed both refs | ✅ `grep "workflow-analysis\|HARNESS_AND_SKILLS_AUDIT" harness/.claude/README.md` → no output |

> **Drift model note (ABS-94)**: live `.claude/README.md` still carries the old refs at lines 155,375 — this is correct and expected. The live `.claude/` is `generated(pin v2.21.2)` and is NOT updated until promotion (ABS-95). The harness source (`harness/.claude/`) is fixed. Verified by diff: `harness/.claude/README.md` clean; `.claude/README.md` carries the pre-fix state per the pin. Parity test confirms this is the intended drift model.

### Harness references to missing files

| Finding | Claim | QAS Verified |
|---------|-------|--------------|
| Template refs in `bsa.md` → `specs/spec_template.md` | Repointed to `specs_templates/` (6 refs) | ✅ All 6 refs now use `specs_templates/` |
| Template refs in `system-architect.md` | Repointed to `specs_templates/` (2 refs) | ✅ Both refs updated |
| Template refs in `spec-creation/SKILL.md` | Repointed to `specs_templates/` | ✅ Updated; `specs_templates/spec_template.md` + `planning_template.md` exist |
| ADR paths in 4 POPM-designated prescribing files | All → `adrs/` per POPM decision | ✅ `system-architect.md`, `AGENT_OUTPUT_GUIDE.md`, `update-docs.md`, `confluence-docs/SKILL.md` all prescribe `adrs/` (verified grep on each) |
| Pattern stubs (security ×3, documentation ×3) | Created with `Status: stub` label; indexed in README | ✅ All 6 stubs exist; `Status: stub` present in first paragraph; patterns_library/README.md has `(stub)` labels |
| `spec-creation` example patterns (modal-form, crud-endpoint, rls-user-data) | Repointed to real existing patterns | ✅ Now reference `form-with-validation.md`, `user-context-api.md`, `rls-migration.md` (all exist) |
| Skill READMEs for duplicate-detection + issue-enrichment | Added in harness source | ✅ `harness/.claude/skills/duplicate-detection/README.md` and `harness/.claude/skills/issue-enrichment/README.md` both exist with correct format |

### Relative-link sweep over all 23 touched files

**Result: CLEAN (0 broken relative markdown links)**

Method: extracted all `[text](relative-url)` links from 23 touched `.md` files, resolved against each file's directory, checked existence. Zero broken links found.

### ⚠️ Follow-up flag (not a blocking AC1 violation — not in enumerated finding set)

`harness/.claude/skills/spec-creation/SKILL.md:249` contains:
```
| ADRs | `docs/adr/ADR-{number}-{description}.md` |
```
This is a plain-text table cell (not a hyperlinked reference), so the link check correctly does not flag it. It was NOT in the ticket's enumerated findings, and NOT among the POPM-designated four prescribing files. However, `docs/adr/` does not exist. The architect's claim of "zero residual `docs/adr/` prescriptions" was imprecise — one instance remains in the spec-creation skill's Output Locations table. Recommend adding to a follow-up reconciliation ticket (alongside the implementer's two flagged out-of-scope items).

---

## AC2 — Per-item decisions recorded ✅

Eight-item decision table present in the implementer handoff and reproduced in PR description:

| Item | Decision |
|------|----------|
| MODERNIZATION-444 whitepaper | Remove |
| Harness audit dir refs | Remove |
| spec/planning templates | Repoint → `specs_templates/` |
| ADR path | Repoint → `adrs/` (POPM decision) |
| security patterns (rls-validation, api-security-audit, vulnerability-scan) | Create stubs |
| documentation/ category (feature-guide, api-reference, migration-guide) | Create stubs |
| spec-creation example patterns | Repoint → existing real patterns |
| confluence-docs phantom ADR table | Trim → pointer to `adrs/README.md` |

✅ All decisions match the implemented state verified in AC1.

---

## AC3 — Harness edits in `harness/.claude/` source; parity + pre-release-check pass ✅

### Parity test: 4/4 PASS (confirmed independently)

```
=== governor drift guard (live .claude == generated(pin)) ===
  pin tag: v2.21.2
  PASS  generate-governor.sh --check passes (live .claude == generated(v2.21.2) + banner stamped)
  PASS  no LOCAL-RUNTIME item is part of the generated shipped set
  PASS  generator explicitly excludes LOCAL-RUNTIME items from generation
  PASS  live settings.template.json wrong-entry-guard registration matches generated(v2.21.2)
=== Test Results ===
  Total: 4 | Passed: 4 | Failed: 0  ✅ ALL TESTS PASSED
```

All harness edits are confirmed in `harness/.claude/` source. Live `.claude/` is correctly pinned to `v2.21.2` per ABS-94/95 drift model.

### Pre-release-check environmental failures (classification: environment — not blocking)

Two test suites have failures traceable exclusively to tracker unreachability:

- **test-hooks-behavioral.sh**: 23/25 PASS, 2/25 FAIL — both failures: `"tracker unreachable or unknown ticket DEMO-2; allowing (fail-open)"` — iteration-guard at-cap tests that require live tracker connectivity
- **test-iteration-guard.sh**: 36/46 PASS, 10/46 FAIL — all 10 failures: `"tracker unreachable or unknown ticket DEMO-{5,6,14,16,19}; allowing (fail-open)"` — tests requiring tracker reads of DEMO-* fixtures

All failures carry the identical signature: `WARN tracker unreachable or unknown ticket DEMO-N; allowing (fail-open)`. None touch any file modified by this ticket. These are **classification: `environment`** failures — the test environment lacks a reachable tracker with the DEMO-* ticket fixtures. Not a bounce cause (ABS-36).

---

## AC4 — knowledge/ + task-tracking.md agree with statuses.yaml and shipped adapters (incl. assign) ✅

| Check | Expected | Found |
|-------|----------|-------|
| `knowledge/index.md` status count | 26 canonical | ✅ Line 14: "26 canonical" |
| `knowledge/ticket-lifecycle-and-statuses.md` status count | 26 canonical | ✅ Line 16: "26: 10 v1 core + 16 v3 workflow" |
| `profiles/neutral/adapters/statuses.yaml` actual count | 26 `- name:` entries | ✅ `grep -c "  - name:" statuses.yaml` = 27; minus 1 comment line = **26 real status entries** |
| `assign_ticket` in `knowledge/ticket-lifecycle-and-statuses.md` | Present (12 ops) | ✅ Line 118: lists `assign_ticket`; line 119: "(twelve operations; assign_ticket sets the assignee at spawn time — ABS-126)" |
| `assign_ticket` in `profiles/neutral/adapters/task-tracking.md` | Present | ✅ Line 51: full `assign_ticket(id, accountId)` entry with ABS-126 reference |
| `assign` in `scripts/mock-tracker.sh` | Implemented | ✅ Line 653: `assign)  cmd_assign "$@"` |
| `.harness-manifest.schema.json` sync_scope enum | Includes `harness/.claude/` | ✅ Enum: `["harness/.claude/", ".claude/", ".gemini/", ".codex/", ".cursor/", ".agents/", "dark-factory/"]` |

---

## Guardrails Check ✅

- No new content beyond stubs/disclaimers ✅
- `docs/releases/` and `docs/archive/` untouched ✅
- `profiles/` (statuses.yaml comment, HARNESS_CHANGELOG.yml) left untouched — confirmed outside scope ✅

---

## Summary Verdict

| AC | Status | Notes |
|----|--------|-------|
| AC1 — Links resolve/removed; link check clean | ✅ PASS | 0 broken links in 23 touched files; all enumerated refs fixed |
| AC2 — Per-item decisions recorded | ✅ PASS | 8-item table in PR; decisions match implementation |
| AC3 — Harness source edits; parity + pre-release pass | ✅ PASS | 4/4 parity; env failures pre-existing, unrelated |
| AC4 — knowledge/ + task-tracking agree with statuses + adapters | ✅ PASS | 26 statuses, 12 ops incl. assign — all sources agree |

**Follow-up ticket recommended (3 items):**
1. `harness/.claude/skills/spec-creation/SKILL.md:249` — residual `docs/adr/` table cell (not in enumerated scope)
2. `patterns_library/api/bonus-content-delivery.md` — dangling ref in untouched pattern-discovery/api-patterns SKILLs
3. `profiles/neutral/adapters/statuses.yaml:7` comment — cites deleted DRAFT spec

---

## Final Verdict

> **✅ APPROVED for RTE**
> QAS validation complete for ABS-147. All four acceptance criteria PASS. Evidence confirmed by independent existence-check. Approved for RTE.

**QAS**: qas | **Date**: 2026-07-08 | **Iteration**: First pass — no prior QAS bounce
