# QA Validation — ABS-215

**Ticket**: ABS-215 — Shared-File-Konflikt-Magneten entschaerfen (Test-Monolith-Append, SOP-Versions-Header)
**Branch**: ABS-215-auto
**Commits**: `b2c273f`, `f79bb79`, `7e64eb1` (3 atomic commits, +161/-1, 6 files)
**QAS run**: 2026-07-12
**Verdict**: **APPROVED**

---

## AC1 — Per-story test files; suite stays green

**Status: PASS**

`tests/test-orchestrator.sh` sources every `tests/orchestrator.d/*.sh` into its own shell just before the results tally (line 3962–3971). The include dir derives from `${BASH_SOURCE[0]}`, not `$SCRIPT_DIR` — a real correctness fix because a helper sourced mid-suite reassigns `$SCRIPT_DIR` to `scripts/`, which would have pointed the include at the wrong directory.

`tests/orchestrator.d/ABS-215-per-story-include.sh` exists and runs 3 asserts:
- harness function `assert_contains` in scope
- harness function `orch` in scope
- `orch --dry-run --once` produces `instance-id:` through the shared driver

**Suite results (two independent runs, both consistent):**

```
Total:  599   Passed: 592   Failed: 7
=== Story tests: ABS-215-per-story-include.sh ===
  PASS  ABS-215: per-story include shares the harness (assert_contains in scope)
  PASS  ABS-215: per-story include shares the orch driver
  PASS  ABS-215: per-story file can drive orch --dry-run --once
```

The 7 failures are pre-existing and orthogonal to this diff: 2 harness-provenance path mismatches (test run from `tmp/ABS-215-work` worktree, not repo root) and 5 model-label/turn-cap default mismatches. The system architect ran a pre-ABS-215 baseline and the `reconcile … exactly once` failures reproduce without the change. This diff adds zero new failures.

New story tests now go in `tests/orchestrator.d/<TICKET>-<slug>.sh` — no shared append region.

---

## AC2 — SOP version line conflict-free

**Status: PASS**

`.gitattributes` carries:
```
docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md merge=union
```

Verified via `git check-attr merge docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md` → `merge: union`.

`docs/sop/ORCHESTRATOR_SOP.md` line 4 now reads:
```
**Version**: 1.6 — per-ticket history is the append-only change log (ABS-215: add a **new line** there, never edit this parenthetical …)
```

`docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md` carries 10 seeded entries, an explicit `<!-- APPEND BELOW -->` marker, and a rule against editing prior lines. The `union` driver ships with git — no `[merge "union"]` config required.

The system architect independently proved the mechanism: concurrent appends on two isolated branches merge CLEAN (exit 0, 0 conflict markers) with the attribute, vs CONFLICT (1 marker) without it.

---

## AC3 — Implementer-seat doc

**Status: PASS**

`docs/sop/TEST_SUITE_LAYOUT.md` exists (72 lines). It covers:
- Section 1: where orchestrator tests go (`tests/orchestrator.d/<TICKET>-<slug>.sh`), file rules (no shebang, no re-source, no counter reset), template reference, and the `bash tests/test-orchestrator.sh` invocation
- Section 2: how to append a SOP changelog line (never edit the header or prior lines), why `union` works, and what defeats it

---

## Files changed (diff `99d9c64...HEAD`)

| File | Change |
|------|--------|
| `tests/test-orchestrator.sh` | +26 lines: include loop before results tally |
| `tests/orchestrator.d/ABS-215-per-story-include.sh` | new: template + 3 self-check asserts |
| `.gitattributes` | +9 lines: `merge=union` for the changelog |
| `docs/sop/ORCHESTRATOR_SOP.md` | -1/+1: header line replaced with pointer |
| `docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md` | new: 25 lines, seeded history |
| `docs/sop/TEST_SUITE_LAYOUT.md` | new: 72 lines, implementer guide |

---

## DoD checklist

- [x] All 3 ACs verified with direct evidence
- [x] Suite: 599/592/7 — zero new failures introduced
- [x] `merge=union` attribute confirmed via `git check-attr`
- [x] Implementer doc complete (both conventions covered)
- [x] Scope held to the 3 ACs — no drive-by refactors
- [x] No RLS/auth/DB/security surface touched
- [x] Commit format: SAFe atomic, one logical change each

---

**Final verdict: APPROVED — transitioning to Story Acceptance.**
