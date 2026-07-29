# QA Validation — PILOT-65

**Ticket**: PILOT-65 — Turn-Caps aus der Messung kalibrieren + die vier Rollen ohne eigenen Cap  
**Branch**: `PILOT-65-auto`  
**Commits under review**: `ad6bf089` (turn-cap calibration) + `4efe4ef3` (rule-ledger anchor fix)  
**QAS run**: 2026-07-26, second pass (first pass bounced for ledger sync)  
**Verdict**: **APPROVED**

---

## AC Verification (code-level, not prose)

All four ACs were verified against the source at `ad6bf089` (unchanged by `4efe4ef3`).

### AC1 — Caps calibrated with documented margin above observed maximum

`builtin_role_max_turns` in `scripts/orchestrator.sh` follows `cap = ceil_to_10(observed_peak × 1.5)`:

| Role | Old cap | Observed max/median | New cap |
|---|---|---|---|
| `qas` | 80 | max 119 | 180 (119 × 1.5 = 178.5 → 180) |
| `tech-writer` | 50 | median 53 | 80 |
| `system-architect` | 40 | median 40 | 60 |
| implementer (`be/fe/data`) | 90 | peak ~90 | 140 (`ORCH_MAX_TURNS_IMPLEMENTER`) |

Each cap now sits **above** the observed maximum. The prior qas cap (80) was below its observed max (119). PASS ✓

### AC2 — Every role has an explicit cap; no silent fall to global 25

- `ui-ux-design`, `qas-design`, `data-provisioning-eng`, `security-engineer` return `50` explicitly in `builtin_role_max_turns`.
- `ORCH_MAX_TURNS_DEFAULT_ROLE=50` introduced.
- `run_spawn_cmd` uses three-branch resolution: explicit operator cap → implementer default (140) → `ORCH_MAX_TURNS_DEFAULT_ROLE` (50). No path reaches the lean 25 for a non-operator-capped seat. PASS ✓

### AC3 — Turn-cap abort is its own logged blocker class and budget-neutral

`blocker_class` in `scripts/orchestrator.sh` has a `turn-cap` case (`*error_max_turns*|*"turn ceiling"*|*max_turns*|*"turn cap"*|*"turn-cap"*`) placed before `transient`. Prior `error_max_turns` entries removed from the `transient` case.

Budget-neutrality via existing machinery:
- `INFRA_ABORT_RE` in `scripts/hooks/iteration-guard.sh` already contains `error_max_turns|max_turns|turn ceiling` — the guard excludes these from the iteration counter.
- `rework_count` skips `actor: orchestrator` transitions (lines confirmed in the awk body); the orchestrator-actor route carries cap-recovery transitions.

PASS ✓

### AC4 — Cap abort never billed as functional bounce

`turn-cap` precedes `logic` in `blocker_class`. Test confirms: `blocker_class 'rework: AC not met AND error_max_turns'` → `turn-cap`. The `iteration-guard` excludes it from the bounce counter. PASS ✓

---

## Test Run (staged suite, HEAD `4efe4ef3`, 2026-07-26)

```
Stage orch-core : 741/741 PASS (262s) — covers changed blocker_class / builtin_role_max_turns / run_spawn_cmd; HEAD 4efe4ef37315
Stage stories   :  51/51  PASS (176s) — HEAD 4efe4ef37315
Stage pool      :  18/19  (226s)      — 1 failure (see below)
```

### Pool stage — pre-existing failure, not a regression

`test-rule-ledger.sh` fails because `.claude/agents/tdm.md` has two headings with no ledger rows (Ops-Sweep PILOT-42, Tier activation PILOT-43). **Identical on baseline `cc1ea37e`** (independently confirmed via throwaway worktree): the gap entered with the v2.32.0 governor promote and predates PILOT-65. Both PILOT-65 commits leave `tdm.md` untouched.

`test-adr-reference-lint.sh` appeared in the pool FAILED list once. **It passes 6/6 in every isolated run** (standalone, private-TMPDIR isolation, baseline cc1ea37e). ADR reference linting has no surface overlap with `docs/rule-ledger.yaml`. The appearance is a parallel-execution (xargs -P4) fluke, not a regression.

Net delta vs baseline: **zero new failures**.

---

## ABS-453 Green-Run Proof (test file modified by this ticket)

`tests/test-orchestrator.sh` was changed in `ad6bf089`.

```
Stage orch-core: 741/741 PASS — command: bash tests/staged-suite.sh --stage orch-core
Commit: 4efe4ef37315a58396c60bca0efd8f5cb73d4394
```

---

## Rule-Ledger Fix Verified (`4efe4ef3`)

`4efe4ef3` changes one line in `docs/rule-ledger.yaml`: R-0295 heading updated from `"Turn-ceiling resolution (ABS-156)"` to `"Turn-ceiling resolution (ABS-156, calibrated PILOT-65)"`. After the fix:

```
scripts/rule-ledger-check.sh output:
RULE-LEDGER: C4: .claude/agents/tdm.md has headings with no ledger row (pre-existing, baseline)
```

The ORCHESTRATOR_SOP.md dangling anchor from my first-pass bounce is resolved.

---

## Verdict: APPROVED

All four ACs met. Staged suite result is on par with baseline. No new regressions introduced by either commit. Transitioning to Story Acceptance.
