# QA Validation Report — ABS-261

**Ticket**: ABS-261 — Orchestrator-Dispatch: priority-aware Slot-Vergabe (hotfix zieht an Feature-Arbeit vorbei)
**Branch**: ABS-261-auto
**Commits**: afe4f15, 148d52d
**QAS Run Date**: 2026-07-15
**Verdict**: ✅ APPROVED

---

## Validation Summary

| Check | Result |
|-------|--------|
| Full orchestrator test suite (TEST_JOBS=1, serial) | **997/997 PASS, 0 failures** |
| ABS-261 specific assertions (16/16) | **16/16 PASS** |
| `bash -n` syntax check — orchestrator.sh | **PASS** |
| `bash -n` syntax check — mock-tracker.sh | **PASS** |
| `generate-governor.sh --providers --check` (ABS-317) | **OK** |

---

## Acceptance Criteria Verification

### AC1 — Priority-ordered slot allocation at cap
> Bei mehr dispatchbaren Tickets als freien Slots werden Slots in Prioritäts-Reihenfolge vergeben (hotfix > high > normal > low; innerhalb gleicher Priorität Alter ASC). Test mit Cap=1 und gemischter Menge.

**Status: ✅ PASS (4 assertions)**

Independent evidence:
- `prioritize_rows()` function applies `priority_rank` (hotfix=0, high=1, normal=2, low=3) with stable zero-padded sequence tiebreak → age-ASC within a band.
- Reconcile sweep pipes `reconcile_rows` through `prioritize_rows` when `ORCH_PRIORITY_DISPATCH != 0` (line 5762-5764 of orchestrator.sh).
- Test assertions at cap=1, bonus=0:
  - `PASS ABS-261 AC1: the hotfix takes the single free slot ahead of key-earlier tickets`
  - `PASS ABS-261 AC1: the normal ticket is deferred (rested), not spawned`
  - `PASS ABS-261 AC1: the low ticket is deferred (rested), not spawned`
  - `PASS ABS-261 AC1: the low ticket does NOT get the slot`

### AC2 — Hotfix cap overrun (ORCH_HOTFIX_CAP_BONUS), no preemption
> priority=hotfix darf den Cap um +1 überziehen (ORCH_HOTFIX_CAP_BONUS, Default 1) — laufende Seats werden NIE gekillt (keine Preemption).

**Status: ✅ PASS (4 assertions incl. control)**

Independent evidence:
- `spawn_dispatch()` computes `eff_cap = ORCH_MAX_CONCURRENT + ORCH_HOTFIX_CAP_BONUS` when `cap_prio = hotfix` (line 6299 orchestrator.sh). Gate RAISES admission ceiling; running seats are never touched.
- Test assertions at cap=1, bonus=1 with 3 hotfixes:
  - `PASS ABS-261 AC2: first hotfix spawns (base slot)`
  - `PASS ABS-261 AC2: second hotfix spawns via the +1 cap bonus (overruns cap=1)`
  - `PASS ABS-261 AC2: the third hotfix defers once the cap+bonus ceiling is reached`
  - `PASS ABS-261 AC2 control: bonus=0 gives hotfix no extra slot (exactly one spawns)`

### AC3 — Adapter dump as priority source; absent priority → normal; backward compat
> Prioritätsquelle ist der Adapter-Dump; fehlt das Feld, gilt normal — volle Abwärtskompatibilität.

**Status: ✅ PASS (2 assertions)**

Independent evidence:
- `ticket_priority()` reads adapter dump's `priority` field via `fm_field`; `case` fallthrough to `normal` for absent/blank/unknown values (lines 1606-1614 orchestrator.sh).
- Spawn decisions on a no-priority tree are byte-identical feature-on vs feature-off (only DEFER-CAP note differs).
- Test assertions:
  - `PASS ABS-261 AC3: key-first ticket keeps the slot when all priorities are absent (=normal)`
  - `PASS ABS-261 AC3: spawn decisions are identical feature-on vs feature-off (backward compat)`

### AC4 — DEFER-CAP intents name the priority (observability)
> DEFER-CAP-Intents nennen die Priorität (Beobachtbarkeit: Operator sieht, WER wem vorgezogen wurde).

**Status: ✅ PASS (2 assertions)**

Independent evidence:
- `spawn_dispatch()` sets `cap_note="priority=$cap_prio"` and passes it to `intent DEFER-CAP … "$cap_note"` (lines 6298, 6304, 6309 orchestrator.sh).
- Test assertions:
  - `PASS ABS-261 AC4: DEFER-CAP names the priority (operator sees who was preferred)`
  - `PASS ABS-261 AC4: DEFER-CAP names a low priority too`

### AC5 — Kill-switch ORCH_PRIORITY_DISPATCH=0 restores legacy order + note-less DEFER-CAP
> Kill-Switch nach ABS-111-Muster (ORCH_PRIORITY_DISPATCH=0 -> Legacy-Reihenfolge), Header-Doku + ORCHESTRATOR_SOP.

**Status: ✅ PASS (3 assertions + static doc checks)**

Independent evidence:
- Kill-switch at line 5762: `if [ "$ORCH_PRIORITY_DISPATCH" != "0" ]`; OFF path skips `prioritize_rows` → legacy key order.
- At line 6295-6300: with switch OFF, `cap_note=""` → `intent DEFER-CAP … ""` (note-less, byte-identical to pre-ABS-261).
- Header doc block in orchestrator.sh lines 27-31: `ORCH_PRIORITY_DISPATCH` and `ORCH_HOTFIX_CAP_BONUS` documented.
- ORCHESTRATOR_SOP.md: both knobs documented in the env-var table with defaults, semantics, and ABS-111 kill-switch reference. ✅
- ORCHESTRATOR_SOP_CHANGELOG.md: entry at line 37. ✅
- Test assertions:
  - `PASS ABS-261 AC5: switch=0 restores legacy key order (low ticket, created first, keeps the slot)`
  - `PASS ABS-261 AC5: the hotfix is deferred under legacy order (no priority preference)`
  - `PASS ABS-261 AC5: switch=0 emits a note-less DEFER-CAP (byte-identical to pre-ABS-261)`

### AC6 — Seats never raise priority (charter in _common-rules)
> Seats erhöhen Prioritäten nie (Charter-Zeile in _common-rules; nur Human/PO setzt hotfix).

**Status: ✅ PASS (1 assertion + static check)**

Independent evidence:
- `harness/claude/agents/_common-rules.md` §12 "Prioritäts-Charter (never raise a ticket's priority, ABS-261)" at line 238. Contains "never raise a ticket's priority". ✅
- Section is prepended to every seat by the spawn seam (ABS-174), so all roles inherit the prohibition.
- Test assertion:
  - `PASS ABS-261 AC6: _common-rules carries the priority charter line (seats never raise priority)`

---

## Regression Check

- Regression introduced and self-fixed by developer within this ticket:
  - First commit's `new_env` also unset `ORCH_ASYNC_SPAWNS`, resetting it from the suite's global pin (`=0`, line 41 of test-orchestrator.sh) to the async default — broke 6 sync-dependent `--live` timing tests.
  - Fixed in commit 148d52d: `new_env` now unsets only `ORCH_PRIORITY_DISPATCH` and `ORCH_HOTFIX_CAP_BONUS`.
  - Confirmed: line 102 of test-orchestrator.sh on ABS-261-auto branch: `unset ORCH_PRIORITY_DISPATCH ORCH_HOTFIX_CAP_BONUS   # ABS-261 priority dispatch (NOT ORCH_ASYNC_SPAWNS: the suite pins it =0 globally at line 41)`
  - Suite on ABS-261-auto: **997/997, 0 failures** (no regression).

---

## Non-Blocking Observations (forwarded from arch review, no QAS action)

Architecture review (2026-07-15T14:27:47Z) noted two adapter-side items for a follow-up ticket:
1. `prioritize_rows` calls `tracker get` per row on live (jira `search` doesn't surface `priority` column).
2. AC1 age-ASC tiebreak is adapter-native order on live (Jira default, not strict age-ASC).

Neither is a defect in the delivered implementation; both are bounded by the kill-switch and existing fence. Recommended as one follow-up adapter change (jira `search` emit `priority` + `ORDER BY created ASC`).

---

## Flags Check (exit routing)

Ticket labels: `[orchestrator-ready]` — no `design` flag.
**Exit target: Story Acceptance** (pipeline: In Test → Story Acceptance; no Design Test gate).

---

## Final Verdict

**APPROVED** — All 6 ACs met, all 16 ABS-261 assertions PASS, full suite 997/997 clean (serial run, exit 0). Bash syntax, governor check, and doc completeness all verified. Implementation is backward-compatible and includes a proper ABS-111-pattern kill-switch.
