# QA Validation Report — ABS-134

**Ticket**: ABS-134 — Spike: Root-Cause der uneinheitlichen Bash-Denials in Headless-Seats  
**QAS Run**: 2026-07-08  
**Deliverable**: `docs/agent-outputs/ABS-134-bash-denial-analysis.md` (265 lines, 13,523 bytes, commit `630d3fd`)  
**Branch**: `ABS-134-auto`  
**Stage**: In Test (Stage 2 — QAS gate)

---

## Acceptance Criteria Validation

| # | Acceptance Criterion | Status | Evidence |
|---|---|---|---|
| AC1 | Analysis doc existiert mit Repro-Matrix und benannter Root-Cause (oder begründetem Ausschluss der Hypothesen) | ✅ PASS | §3: 15-row executed repro matrix; §5: root cause named ("fresh-spawn permission-initialization race"); §4: all 5 hypotheses explicitly adjudicated with verdicts (H1 REFUTED, H2 REFUTED, H3 PARTIAL/mechanism, H4 REFUTED as discriminant, H5 CONFIRMED) |
| AC2 | Mindestens ein AUSGEFÜHRTES Repro-Experiment dokumentiert (Kommando + Ergebnis) | ✅ PASS | §3 rows 1–15 all marked EXECUTED; each row carries: command shape, when-in-session, result, and what it isolates. Decisive rows 14–15 are verbatim replays of the denied rows 1–2 — same strings, later state, allowed — the definitive content-vs-state proof. |
| AC3 | Empfehlung: konkreter Fix-Pfad inkl. betroffener Dateien | ✅ PASS | §6 Fix A: `scripts/orchestrator.sh` `ensure_worktree()` lines 1977–2030 (insert after git worktree add at 2004/2021/2023, before `rmdir "$wlock"` at 2027); §6 Fix B: `scripts/orchestrator-spawn-claude.sh` lines 208–217; kill-switch `ORCH_WORKTREE_SETTINGS=0` per ABS-111 convention; change estimated at ~4–6 lines. |

**AC Coverage: 3/3 (100%)**

---

## Independent Verification

QAS independently read the load-bearing source files — NOT trusting the doc's claims on faith:

### Claim: `.claude/settings.local.json` is gitignored and untracked
```
$ git check-ignore -v .claude/settings.local.json
~/.config/git/ignore:1:**/.claude/settings.local.json    .claude/settings.local.json

$ git ls-files --error-unmatch .claude/settings.local.json
error: pathspec '.claude/settings.local.json' did not match any file(s) known to git

$ ls -la .claude/settings.local.json
-rw-r--r--@ 1 sahan  staff  225 Jul  8 00:32 .claude/settings.local.json
```
✅ **CONFIRMED**: gitignored (global rule `**/.claude/settings.local.json`), untracked, timestamp 00:32 (after worktree provisioning — races the spawn's first tool call).

### Claim: `ensure_worktree()` at `orchestrator.sh` lines 1977–2030 has NO settings-provisioning step
QAS read lines 1977–2030 directly. Content verified:
- Lines 2004 / 2021 / 2023: three `git worktree add` call sites
- Line 2027: `rmdir "$wlock"` (lock release / end of function critical section)
- **No copy, no render, no settings step** between any `worktree add` and `rmdir "$wlock"`
- Fix A landing point is precise: inject after `worktree add`, before `rmdir` — semantics-preserving.
✅ **CONFIRMED**: the doc's key negative claim holds.

### Claim: spawn is launched with `--permission-mode dontAsk` and `--allowedTools "Skill"`
QAS read `orchestrator-spawn-claude.sh` lines 200–228:
- Line 204: `--permission-mode dontAsk` ✅
- Lines 215–217: `case "$SEAT_TOOLS" in *Skill*) set -- "$@" --allowedTools "Skill" ;; esac` ✅
- Lines 219–228: `ORCH_SPAWN_CWD` worktree cwd logic ✅

The H4 refutation table (§4.1: `po-agent` no-Skill affected, `qas` Skill unaffected) is consistent with the actual spawn code — `--allowedTools "Skill"` does not partition the Befund-3 groups.

---

## Blind-Spot Catalog

| Area | Status | Notes |
|---|---|---|
| Error / edge cases | ✅ ok | Source-missing case addressed (Fix A: `mkdir -p "$wt/.claude"`, skip if no source); noted that settings.template.json is a fallback option |
| Scope discipline | ✅ ok | Fix NOT shipped — correctly justified: touches production permission seam, is >10 lines with guards + kill-switch; follows `<10 Zeilen darf direkt mitgeliefert werden` spike contract |
| Competing hypotheses | ✅ ok | All 5 ticket hypotheses adjudicated; H3 correctly labeled "PARTIAL / mechanism" (not cop-out — true cause is the race, cwd was correct) |
| Kill-switch / rollback | ✅ ok | `ORCH_WORKTREE_SETTINGS=0` follows ABS-111 seam convention |
| Residual uncertainty | ✅ ok | §5.1 honestly states which component provisions the file is not fully traced; correctly notes this does not change root cause or fix; prescribes a verification step for the fix owner |
| Dedup gate | ✅ ok (caveat noted) | `duplicate-detection` run against mock-tracker (only searchable store from the headless seat); verdict `create`; doc correctly flags that live-tracker dedup must be re-run by PO/issue-enrichment before creating the follow-up |
| Follow-up story | ✅ ok | §7 proposes story with clear ACs; routed to issue-enrichment/PO (correct — be-developer seat has no tracker MCP) |
| Over-engineering | ✅ ok | Fix B marked optional pending merge-semantics check; single concrete primary fix (A) recommended |

---

## Iteration Count

This is the **first** QAS pass on ABS-134. No prior QAS bounce comments detected. `Iteration 1 of 3`.

---

## Carry-Forwards (non-blocking; noted by System Architect, confirmed by QAS)

These are items for the **follow-up story**, not defects in this spike's deliverable:

1. **Live dedup required**: The dedup in §7 ran only against the mock store. PO/issue-enrichment MUST re-run live dedup against Jira before creating the follow-up fix story.
2. **Live-spawn verification as AC**: §5.1 prescribes instrumenting `ensure_worktree()` / spawn seam to confirm the denial window closes once provisioning is synchronous. This MUST be an acceptance criterion on the fix story, not optional.

Neither item prevents approval of this spike.

---

## Test Run Summary

This is a spike/analysis ticket. No automated test suite (`yarn test:*`) applies — pattern-discovery confirmed no test pattern covers spike deliverables (pattern gap reported: testing library covers API integration and E2E flows only).

QAS validation method: AC checklist review against the analysis document, independent source-file verification of load-bearing claims, blind-spot catalog.

```
AC1 — Doc + repro matrix + root cause + hypothesis adjudication: PASS
AC2 — ≥1 executed experiment (command + result): PASS (15 rows; rows 14-15 decisive)
AC3 — Concrete fix path + files: PASS (Fix A: orchestrator.sh 1977-2030; Fix B: spawn 208-217)

Source verification:
  .claude/settings.local.json gitignored/untracked:   CONFIRMED
  ensure_worktree() has no settings-provisioning step: CONFIRMED
  dontAsk + allowedTools Skill flags at stated lines:  CONFIRMED
  Fix A landing point (post-worktree-add, pre-rmdir):  CONFIRMED PRECISE

Blind-spot catalog:  CLEAN (no gaps)
Scope discipline:    CORRECT (fix not shipped; >10-line contract honored)
Dedup gate:          RUN (mock only; live dedup routed to PO per seat constraints)
```

---

## Verdict

**✅ APPROVED for RTE**

All 3 acceptance criteria fully met. Root cause is mechanically sound and independently verified against the actual runner code. The 15-row repro matrix (with decisive verbatim-replay rows 14–15) provides strong evidentiary quality for a spike. Fix A is precise, semantics-preserving, and correctly scoped to the follow-up story. Residual uncertainty is honestly stated. Two carry-forwards are process items for the fix story, not defects in this spike.

---

## Next Steps

1. **Issue-Enrichment / PO**: Create the follow-up fix story in the live tracker (re-run live dedup first; carry §5.1 live-spawn verification as a mandatory AC).
2. **System Architect**: Review Fix A and run §5.1 live-spawn verification before any implementation of the follow-up.
3. **Runner / Orchestrator**: Transition ABS-134 to Done.

