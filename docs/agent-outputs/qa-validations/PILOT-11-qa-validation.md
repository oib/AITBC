# QA Validation Report — PILOT-11

**Ticket**: PILOT-11 — Enabler: seat-independent merge chokepoint (unskippable PreToolUse guard)
**Branch**: PILOT-11-auto
**QAS run date**: 2026-07-23 (re-validation; first gate 2026-07-22)
**Verdict**: ✅ APPROVED

---

## Re-Validation Summary (ae497912 — forward-fix for knob-drift)

Forward-fix commit `ae497912` added one row to the `docs/sop/ORCHESTRATOR_SOP.md`
Environment Knobs table documenting the `ORCH_MERGE_GUARD` kill-switch that was
present in `scripts/orchestrator.sh` (commit `b7c97d31`) but previously undocumented,
causing `tests/test-orch-knob-drift.sh` to fail in the Epic Integration full-suite.

This re-validation covers `ae497912` (HEAD of `PILOT-11-auto`). AC1–AC4 from the
original gate are re-confirmed; the knob-drift sensor + suite are additionally green.

| AC | Description | Result |
|----|-------------|--------|
| AC1 | Skip-path to main refused before git host; intent line surfaced | ✅ PASS |
| AC2 | Legit epic auto-merge with ORCH_AUTOMERGE=1 still succeeds | ✅ PASS |
| AC3 | rte.md + rte-reference.md duty-step 4 reworded; mirror parity preserved | ✅ PASS |
| AC4 | Green run cited (verbatim command + counter + commit hash, ABS-453) | ✅ PASS |
| SOP | ORCH_MERGE_GUARD knob documented in ORCHESTRATOR_SOP.md | ✅ PASS |

---

## AC4 — Green-run proof (ABS-453) — re-run at ae497912

All four suites run personally by QAS on `PILOT-11-auto` HEAD `ae497912`.

### Suite 1 — PILOT-11 chokepoint (AC1 + AC2 + kill-switch + scope)

```
Command: bash tests/test-merge-guard-chokepoint.sh
Result:  Total: 16 / Passed: 16 / Failed: 0
Commit:  ae49791298c7cdda1b30678a0505740c587332a1
```

Verbatim output:
```
=== PILOT-11 merge chokepoint (pre-bash-merge-guard.sh) ===

A. AC1 — skip path: a main-targeted merge is BLOCKED before the git host
  PASS  bb pr merge -> main -> BLOCK (exit 2, no merge call)
  PASS  bb pr merge -> main -> surfaces MERGE-GUARD-REFUSE … action=hitl-handoff
  PASS  glab mr merge -> main -> BLOCK (exit 2, no merge call)
  PASS  glab mr merge -> main -> surfaces MERGE-GUARD-REFUSE … action=hitl-handoff
  PASS  glab mr merge 150 (the MR !150 form) -> BLOCK

B. AC2 — legit epic merge with ORCH_AUTOMERGE=1 passes the chokepoint
  PASS  glab mr merge -> epic/* + ORCH_AUTOMERGE=1 -> ALLOW (exit 0)
  PASS  bb pr merge -> epic/* + ORCH_AUTOMERGE=1 -> ALLOW (exit 0)

C. Invariance — the ORCH_AUTOMERGE knob never changes the decision
  PASS  main, ORCH_AUTOMERGE=1 -> BLOCK
  PASS  main, ORCH_AUTOMERGE=0 -> BLOCK
  PASS  epic/*, ORCH_AUTOMERGE unset -> ALLOW

D. Scope — only the merge subcommand is intercepted
  PASS  bb pr view (not a merge) -> ALLOW untouched
  PASS  glab mr create (not a merge) -> ALLOW untouched
  PASS  git status (not a merge) -> ALLOW untouched

E. Context + fail-closed + kill switch
  PASS  human shell (no ORCH_SEAT) -> never guarded (exit 0)
  PASS  merge with UNRESOLVABLE target -> fail closed (exit 2)
  PASS  ORCH_MERGE_GUARD=0 -> merge to main allowed (legacy, exit 0)

=== Results ===
  Total:  16
  Passed: 16
  Failed: 0
```

### Suite 2 — PILOT-10 regression (merge-target-guard.sh baseline)

```
Command: bash tests/test-merge-target-guard.sh
Result:  Total: 15 / Passed: 15 / Failed: 0
Commit:  ae49791298c7cdda1b30678a0505740c587332a1
```

### Suite 3 — Knob-doc drift sensor (direct)

```
Command: bash scripts/orch-knob-doc-drift.sh
Result:  exit 0 ("every ORCH_* knob read in scripts/ is documented in the SOP")
Commit:  ae49791298c7cdda1b30678a0505740c587332a1
```

### Suite 4 — Knob-doc drift test suite

```
Command: bash tests/test-orch-knob-drift.sh
Result:  Total: 4 / Passed: 4 / Failed: 0
Commit:  ae49791298c7cdda1b30678a0505740c587332a1
```

---

## AC1 — Skip-path block + MERGE-GUARD-REFUSE intent line

Section A of the chokepoint suite (5 assertions) confirms:
- `bb pr merge` and `glab mr merge` to `main` → blocked at exit 2, merge call never reaches git host.
- The MR !150 exact form (`glab mr merge 150`) → blocked.
- `MERGE-GUARD-REFUSE … action=hitl-handoff` intent line surfaced on every blocked case.

The hook reads the Bash tool's stdin JSON payload via jq, resolves the MR target via
`ORCH_MERGE_GUARD_TARGET_CMD` test seam (or native `glab`/`bb` view), then calls
`scripts/merge-target-guard.sh check <target>`. On protected target: guard exits 1,
hook exits 2 (block) — the merge never reaches the forge.

---

## AC2 — No false-positive on legit epic auto-merge

Sections B + C of the chokepoint suite confirm:
- `epic/*` target → ALLOW (exit 0) for both `glab` and `bb` with `ORCH_AUTOMERGE=1`.
- `ORCH_AUTOMERGE` knob is invariant to the protected-branch decision:
  main → BLOCK regardless of knob value; `epic/*` → ALLOW regardless of knob value.

ADR-A-0014 (epic-branch auto-merge, ABS-88) is unimpeded.

---

## AC3 — Doc reword + mirror parity

**rte.md** (harness/claude/agents/) duty-step 4:
- New: `scripts/merge-target-guard.sh check "<the ACTUAL MR target branch>"` with
  explicit instruction that empty `$EPIC_BRANCH` trips exit 64 (usage error) rather
  than the clean `MERGE-GUARD-REFUSE` intent line; epic-less lane instructed to pass
  `main`.
- No bare `check "$EPIC_BRANCH"` form remains in harness, provider, or docs.

**rte-reference.md** (`docs/sop/`): pre-merge checklist entry updated to match.

**Mirror parity**:
- `diff harness/claude/hooks/pre-bash-merge-guard.sh agent_providers/claude_code/hooks/pre-bash-merge-guard.sh` → byte-identical (confirmed by QAS).
- Hook registered in both `settings.template.json` and `hooks-config.json`.

**ORCH_MERGE_GUARD knob** (`ae497912`):
- Row in `docs/sop/ORCHESTRATOR_SOP.md` Environment Knobs table:
  `| ORCH_MERGE_GUARD | 1 (PILOT-11 merge chokepoint; 0 restores unguarded merges) | orchestrator.sh, hooks/pre-bash-merge-guard.sh |`
- Knob-drift sensor confirms no other undocumented ORCH_* knobs (exit 0).

---

## Files Reviewed

| File | Status |
|------|--------|
| `harness/claude/hooks/pre-bash-merge-guard.sh` | ✅ correct |
| `agent_providers/claude_code/hooks/pre-bash-merge-guard.sh` | ✅ byte-identical mirror |
| `harness/claude/settings.template.json` | ✅ hook registered (PreToolUse Bash) |
| `harness/claude/hooks-config.json` | ✅ hook registered |
| `harness/claude/agents/rte.md` | ✅ duty-step 4 reworded |
| `agent_providers/claude_code/prompts/rte.md` | ✅ mirror-identical |
| `docs/sop/rte-reference.md` | ✅ checklist entry updated |
| `scripts/orchestrator.sh` | ✅ ORCH_MERGE_GUARD kill-switch declared |
| `docs/sop/ORCHESTRATOR_SOP.md` | ✅ ORCH_MERGE_GUARD knob documented (ae497912) |
| `scripts/orch-knob-doc-drift.sh` | ✅ exit 0 (no drift) |
| `tests/test-merge-guard-chokepoint.sh` | ✅ 16/16 |
| `tests/test-merge-target-guard.sh` | ✅ 15/15 |
| `tests/test-orch-knob-drift.sh` | ✅ 4/4 |

---

## Implementation Quality Notes

- **Enforcement layer**: PreToolUse Bash hook fires on every Bash tool call regardless
  of seat cooperation. Spawn seam cannot intercept CLI merge calls inside a seat's shell.
  #PATH_DECISION confirmed correct by architect.
- **Seat-only guard**: Human shells carry no `ORCH_SEAT` marker → never guarded.
- **Fail-closed**: Unresolvable MR target → exit 2 (block), never allows through.
- **Kill switch (ABS-111)**: `ORCH_MERGE_GUARD=0` per ABS-111 pattern; default ON.
- **Observability (ABS-66)**: Blocked merges logged with UTC timestamp, seat ID, target, command.
- **ABS-294 log-injection defence**: Command flattened (newlines stripped) before audit append.

---

## Original Gate Evidence (2026-07-22, commit b7c97d31)

Preserved for traceability. The original QAS gate at `b7c97d31` returned APPROVED
(16/16 + 15/15). The forward-fix at `ae497912` is additive (one SOP table row) and
did not alter any hook, test, or rte.md content. Re-running all suites on `ae497912`
confirms no regression and fully green knob-drift gate.

---

## Final Verdict

**APPROVED** — All 4 ACs met at `ae497912` (HEAD of `PILOT-11-auto`).
Test suites green: chokepoint 16/16, target-guard 15/15, knob-drift 4/4.
The seat-independent merge chokepoint closes the MR !150 / ABS-513 self-merge defect
class mechanically. Approved for Story Acceptance.
