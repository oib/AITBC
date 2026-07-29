# QA Validation — ABS-219

**Ticket**: ABS-219 — self-improvement-Station: Miner-Report als Pflicht-Input des Epic-Done-Seats  
**Branch**: `ABS-219-auto`  
**Commit**: `ebce3b0`  
**QAS run date**: 2026-07-12  
**Verdict**: ✅ APPROVED

---

## Change Summary

Doc-only wiring: `harness/claude/agents/self-improvement.md` + `AGENTS.md`. No runtime code, no DB ops, no RLS/auth/migration surface. Validation scope is content correctness against the four ACs, plus independent verification of every referenced flag, verdict label, and threshold against the actual miner script (`origin/ABS-218-auto:scripts/skill-mining.sh`).

---

## Acceptance Criteria Results

### AC1 — self-improvement.md requires skill-mining.sh first, then retro ✅

Two insertion points in the file enforce the ordering:

**Analysis Flow**: New "Step 0: Skill-Mining Report (MANDATORY FIRST, ABS-219)" inserted before Step 1 (Retro). The step body reads: "Only after reading the miner report do you run the retro (Step 1)."

**Epic Retro Seat Duty** (auto-spawn section): Prior step 2 was "Run the retro." Now:
- Step 2: "Run the miner FIRST (mandatory, ABS-219)" — runs `scripts/skill-mining.sh --proposals --out work/.orchestrator/skill-mining-<epic-id>.md`, reads the report.
- Step 3: "Run the retro."

**Success Criteria**: Updated to prepend: "Skill-mining report (`scripts/skill-mining.sh`) run and read FIRST, before the retro (ABS-219)."

Ordering is unambiguous in every entry point.

### AC2 — per SKILL-KANDIDAT verdict: proposal filed or reasoned rejection, no silent ignoring ✅

**Duty step 4** (new): "Reconcile every SKILL-KANDIDAT verdict (no silent ignoring, ABS-219 AC2)" — for each flagged role: proposal in `work/improvement-proposals/` OR reasoned rejection in the handoff. Explicit rule: "A verdict may never be dropped without a recorded decision."

**Handoff format**: New `SKILL-KANDIDAT reconciliation (ABS-219 AC2)` line: `per candidate → proposal filed (work/improvement-proposals/<file>.md) OR reasoned rejection [why no proposal] — every verdict accounted for, none dropped.`

**Success Criteria**: Updated to include "every `SKILL-KANDIDAT` verdict ends as a filed proposal or a reasoned rejection, never silently dropped."

Coverage is complete: the duty, the handoff template, and the success criteria all enforce the no-silent-ignoring rule.

### AC3 — handoff format names mining metrics (which threshold crossed) ✅

New `Mining metrics (ABS-219 AC3)` line in the handoff template:

```
- **Mining metrics (ABS-219 AC3)**: report `work/.orchestrator/skill-mining-<epic-id>.md`;
  roles analyzed N; `SKILL-KANDIDAT` roles: [role → which threshold(s) crossed, e.g.
  `pattern X 12x/4 seats (>=10x/3)`, `help 4 (>=3)`, `NOMOVE+RESPAWN 3 (>=2)`];
  `OK` roles: [...]. If the miner did not run, state that here.
```

The template names the report path, the role count, and the specific threshold(s) crossed per candidate role. The fallback clause ("If the miner did not run, state that here") ensures the line is present even on miner failure.

### AC4 — AGENTS.md role and seat rows updated ✅

**Role table (line 41)**: Self-Improvement Agent description updated to: "runs `scripts/skill-mining.sh` FIRST (mandatory input, ABS-219), then retro; skill mining + boilerplate improvement proposals." Success column updated: "Miner report read; per `SKILL-KANDIDAT` verdict a filed proposal or reasoned rejection; report."

**Automated-seat table (line 107)**: Epic Retro entry updated to: "`Epic Done` (terminal) → `skill-mining.sh` first (ABS-219), then retro + skill mining, no exit transition."

Both rows verified by `grep -n "Self-Improvement" AGENTS.md`.

---

## Independent Miner Script Verification

Verified against `origin/ABS-218-auto:scripts/skill-mining.sh` (the actual file from the dependency):

| Claim in doc | Script reality | Match |
|---|---|---|
| `--proposals` flag files a skeleton per SKILL-KANDIDAT | Line 67: `--proposals) WRITE_PROPOSALS=1`; line 373: writes skeletons for candidates | ✅ |
| `--out FILE` flag writes report to FILE | Line 68: `--out) OUT=...`; used for output redirect | ✅ |
| Verdict labels: `SKILL-KANDIDAT` / `OK` | Lines 293/295: `"**Verdict: SKILL-KANDIDAT**"` / `"**Verdict: OK**"` | ✅ |
| Threshold: pattern ≥10×/3 seats | `THRESH_PATTERN_COUNT=10`, `THRESH_PATTERN_SEATS=3` (env-overridable) | ✅ |
| Threshold: help ≥3 | `THRESH_HELP_CALLS=3` (env-overridable) | ✅ |
| Threshold: NOMOVE+RESPAWN ≥2 | `THRESH_NOMOVE_RESPAWN=2` (env-overridable) | ✅ |
| One block per role via `render_role` | `render_role` at line 264 emits one block per role with verdict | ✅ |

No invented identifiers. Every flag, label, and threshold in the doc maps to a real line in the script.

---

## Guardrails Check ✅

- No new role introduced.
- Trigger stays Epic Done / PO-Agent (per ABS-4); self-scheduling not added.
- `Epic Done` remains terminal; no exit transition added to the seat.
- "If the script is missing or fails, record that and degrade to retro-only — never skip silently" ensures backward compatibility when the miner is absent.

---

## Validation Method

Doc-only change: no executable test suite applies. Validation ran as:

1. `git show ebce3b0` — full diff read and each AC mapped to inserted lines.
2. `git show origin/ABS-218-auto:scripts/skill-mining.sh` — miner script read independently; all referenced flags/verdicts/thresholds confirmed against actual lines.
3. `grep -n "Self-Improvement" AGENTS.md` — both AGENTS.md rows confirmed.

Working tree is clean (`git status --short` output: empty).

---

## Final Verdict

All four ACs satisfied. Guardrails honored. Every technical claim in the doc verified against the actual miner script. No over-engineering; the change is minimal and scoped exactly to the four ACs.

**Verdict: ✅ APPROVED — ready for Story Acceptance.**
