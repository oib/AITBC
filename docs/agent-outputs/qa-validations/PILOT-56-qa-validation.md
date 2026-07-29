# QA Validation Report — PILOT-56

**Ticket**: PILOT-56 — ADR-reference linter concurrency-safe file-walk  
**Commit**: `23b7d9b9c204cb9247863721d6d0a340cecdd788`  
**Branch**: `PILOT-56-auto`  
**Date**: 2026-07-27  
**Verdict**: APPROVED

---

## AC Results

### AC1 — Pre-fix walk can emit false DANGLING under concurrent mutation
**PASS**

Case 7 reproduced the race on this host. `old_scan()` replays the pre-fix
`find|xargs grep` + `grep -r` pipeline against a tree where
`ADR-A-0001-a.md` cycles through rm+recreate every 3 ms. Within 300 tries
the function emitted a false dangling — the scenario genuinely exercises
the race condition.

### AC2 — Fixed linter stays green across 20 back-to-back runs under that mutation
**PASS**

Case 8 ran the patched `scripts/adr-reference-lint.sh` 20 times against the
same flickering tree. `ac2_red=0`: zero false RED.

### AC3 — All existing test cases green; ABS-315 dangling semantics unchanged
**PASS — 9/9**

```
✓ Case 1: clean tree        → exit 0, no output
✓ Case 2: stale spec ref    → exit 1, DANGLING: ADR-A-0016
✓ Case 3: ADR cross-ref     → exit 1, DANGLING: ADR-A-0404
✓ Case 4: README excluded   → exit 0, no FP
✓ Case 5: placeholder prose → exit 0, no FP
✓ Case 6: real repo tree    → exit 0
✓ Case 7: AC1 witness       → race reproduced
✓ Case 8: AC2 fix           → 20/20 green
✓ Case 9: AC5 unreadable    → skipped cleanly
```

Genuine dangler still exits 1 with the correct `DANGLING:` line (Cases 2, 3).

### AC4 — Pool stage green across 5 consecutive runs
**PASS**

Command: `bash tests/staged-suite.sh --stage pool` (102 test files, `-P4`)

| Run | Files | Result | Duration |
|-----|-------|--------|----------|
| 1   | 102   | PASS   | 274s     |
| 2   | 102   | PASS   | 259s     |
| 3   | 102   | PASS   | 261s     |
| 4   | 102   | PASS   | 324s     |
| 5   | 102   | PASS   | 337s     |

`test-adr-reference-lint.sh` PASS in every run. Zero false RED.

### AC5 — Vanished/unreadable path does not abort the scan
**PASS**

Case 9 created `specs/unreadable.md` (cites undefined `ADR-A-9999`), chmod'd it
to `000`, then ran the linter. Exit 0, no output:
- `2>/dev/null || true` on each `grep` call suppresses unreadable-file errors.
- `[ -f "$f" ] || continue` guards skip any path that vanishes between
  enumeration and read.

---

## Implementation notes (non-blocking)

`scan()` uses two defences against pool-load races:

1. **Snapshot-then-read** — `find` runs once into an array; each path gets an
   existence check before `grep`. A missing file at read time is skipped, not
   an error.
2. **Confirm-before-fail** — a candidate DANGLING must survive `comm -12`
   across up to 5 re-scans (50 ms apart). A transient race miss disappears on
   re-scan; a genuine dangler persists. The confirm loop only runs when the
   first scan returns at least one hit, so the green-path cost is one `scan()`.

Architect noted (non-blocking): the confirm loop only weakens detection if the
`adrs/` + `specs/` scopes themselves mutate mid-lint — not the gate scenario.
Confirmed: no change request.

No `harness/claude/agents|skills` edits — provider mirror regen (ABS-317) not
required.

---

## Verdict

**APPROVED** — AC1 through AC5 all verified green. Pool stage stable across 5
consecutive rounds at `-P4`. ABS-315 guard semantics intact.
