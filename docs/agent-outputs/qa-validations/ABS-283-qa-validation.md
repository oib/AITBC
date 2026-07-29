# QA Validation Report — ABS-283

**Ticket**: ABS-283 — ADR-Nummernkollision: id ADR-A-0022 dreifach vergeben — halb ausgefuehrten Renumber abschliessen + mechanischer Uniqueness-Guard  
**Branch**: `ABS-283-auto`  
**HEAD at validation**: `6933ac3`  
**Commits reviewed**: `d6bc096`, `f5387e3`, `6933ac3`  
**QAS run**: 2026-07-14  
**Verdict**: ✅ **APPROVED**

---

## AC Validation Results

### AC1 — Renames and frontmatter ids ✅ PASS

**Evidence:**
```
ADR-A-0023-session-invalidation-inputs.md  → id: ADR-A-0023  ✓ (file exists)
ADR-A-0025-per-epic-merge-token.md         → id: ADR-A-0025  ✓ (file exists)
ADR-A-0022-session-invalidation-inputs.md  → No such file    ✓ (old name gone)
ADR-A-0022-per-epic-merge-token.md         → No such file    ✓ (old name gone)
ADR-A-0022-agent-def-overlays.md           → id: ADR-A-0022  ✓ (UNCHANGED, ABS-258)
```
Both renames via `git mv` (99% similarity detected), history follows.

---

### AC2 — No duplicate ids; frontmatter id matches filename ✅ PASS

**Evidence:**
```
grep -h '^id:' adrs/agentic/*.md | sort | uniq -d
(empty — zero duplicates)
```
Full frontmatter-vs-filename audit across all 25 agentic ADRs: **zero mismatches**.

---

### AC3 — All living back-references corrected ✅ PASS

**Evidence — short-form sweep (architecture review catch):**
```
git grep -nE "(^|[^-A-Za-z])A-0022" -- . ':!docs/agent-outputs' ':!blueprint'
(empty — zero stale short-form citations)
```

ADR-A-0014 lines 234 and 237 now correctly read `A-0025` (the specific 2-line fix from
the arch review bounce — `A-0022 adds the runner-enforced per-epic merge token` was the
exact ambiguity the ticket exists to close).

**Surviving long-form `ADR-A-0022` hits** — all legitimate ABS-258 overlay references:
- `adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md:302`
- `docs/guides/AGENT_DEF_OVERLAY_GUIDE.md:3,111,155`
- `docs/sop/BOILERPLATE_MIGRATION_SOP.md:336,368`
- `scripts/orchestrator-spawn-claude.sh:43,116,220`
- `tests/test-agent-def-overlay.sh:3`
- `tests/test-migrate-project.sh:114,286,433`
- Historical note in `ADR-A-0024:9-18` (AC7 preserves this)

**Sanity — new ids present in expected locations:**
- `ADR-A-0023`: ADR-A-0002:62, ORCHESTRATOR_SOP.md (×5), orchestrator.sh (×5), test-orchestrator.sh (×2) ✓
- `ADR-A-0025`: ADR-A-0014:232-237, ORCHESTRATOR_SOP.md (×6+link), orchestrator.sh (×6), test-merge-token.sh (×3) ✓

---

### AC4 — Uniqueness guard catches violations ✅ PASS

**Evidence:**
```
bash tests/test-adr-id-uniqueness.sh  →  7 passed, 0 failed  (exit 0)
```

Guard catches: (a) two files sharing a frontmatter id, (b) frontmatter id ≠ filename id,
(c) missing frontmatter id. Fixture self-checks cover one clean positive and both negatives
— cannot pass vacuously.

**Independent negative probe** (run by QAS):
```
# Injected ADR-A-0099-probe.md with id: ADR-A-0025
bash tests/test-adr-id-uniqueness.sh  →  2 failed  (exit 1)  ✓ guard bites
# Probe removed; clean tree exit: 0  ✓
```

---

### AC5 — Auto-discovery; no CI change ✅ PASS

**Evidence:**
```
.github/workflows/tests.yml:60          TESTS=(tests/test-*.sh)          ✓
scripts/pre-release-check.sh:98         for test_file in tests/test-*.sh  ✓
```
`tests/test-adr-id-uniqueness.sh` is auto-discovered by both runners. Zero CI changes needed.

---

### AC6 — No decision content changed ✅ PASS

**Evidence:**
```
grep '^status:' adrs/agentic/ADR-A-0022-agent-def-overlays.md   → status: proposed  ✓
grep '^status:' adrs/agentic/ADR-A-0023-session-invalidation-inputs.md → status: proposed  ✓
grep '^status:' adrs/agentic/ADR-A-0025-per-epic-merge-token.md → status: proposed  ✓
```

Full diff stat: 10 files changed, 176 insertions, 33 deletions.  
Touched: 2 ADR frontmatter `id:` lines, citation lines in `adrs/`, `docs/sop/`, `scripts/`,
`tests/`, plus 1 new test file. No Context/Decision/Consequences altered in any ADR.
ADR-A-0004 guardrail respected — no ADR accepted, no `status:` changed.

---

### AC7 — Protected paths untouched; ADR-A-0024 note intact ✅ PASS

**Evidence:**
```
git diff d6bc096~1..6933ac3 -- docs/agent-outputs/  →  (empty)  ✓
git diff d6bc096~1..6933ac3 -- blueprint/            →  (empty)  ✓
```

`ADR-A-0024:9-18` renumber note is intact. The AC7-permitted optional completion sentence
(`"Plan completed (ABS-283, 2026-07-14)."`) is present and appropriate — it records that
the plan originally documented there is now fully executed.

---

## Summary

| AC | Description | Result |
|----|-------------|--------|
| AC1 | Renames + frontmatter ids correct | ✅ PASS |
| AC2 | No duplicate ids; id/filename aligned | ✅ PASS |
| AC3 | All back-references corrected (incl. short-form A-0022) | ✅ PASS |
| AC4 | Guard catches duplicate ids and id/filename disagreement | ✅ PASS |
| AC5 | Auto-discovered by CI; exit 0 clean / exit 1 injected | ✅ PASS |
| AC6 | No decision content or status changed | ✅ PASS |
| AC7 | Protected dirs untouched; ADR-A-0024 note preserved | ✅ PASS |

**Open items (not blocking, inherited from arch review handoff):**
- `test-orchestrator.sh` is red and flaky at HEAD `bf7e310` — pre-existing, worktree-path-sensitive, count-discrepant (implementer saw 22, arch-review saw 9). Needs an owner and a ticket.
- Root cause (parallel seats grabbing "next number" without reservation) is untouched by design. AC4's guard makes collisions visible, not impossible — prevention belongs in ABS-270/ABS-266 runner family.
- `parent: ABS-278` vs "outside ABS-278" inconsistency awaits epic-acceptance seat.

**Verdict: APPROVED — releasing to Story Acceptance.**

No `design` flag → Story Acceptance (no Design Test gate).
