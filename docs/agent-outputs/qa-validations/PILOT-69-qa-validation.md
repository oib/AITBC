# QA Validation Report — PILOT-69

**Ticket**: PILOT-69 — Taxonomien ohne Wirkung: ADR-A-0018 transient-Klasse und die ADR-A-0024-Advisory  
**Branch**: `PILOT-69-auto`  
**Commit under test**: `b841a342`  
**Merge-base**: `cc1ea37e` (v2.32.0)  
**QAS run date**: 2026-07-26  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria

### AC1 — transient-class gets an effect (budget-neutral for iteration/rework counters + finished-work→Blocked routing)

**PASS**

- `rework_count()` in `scripts/orchestrator.sh` now accepts an `infra_re` awk variable driven by `ORCH_REWORK_INFRA_RE`. A backward transition whose reason matches the infra pattern is skipped — never counted as rework. This mirrors the existing iteration guard (`ABS-555 INFRA_ABORT_RE`) so both counters treat the transient class identically.
- Handoff mis-reports (`ADR-A-0024 (e)`) are deliberately absent from `ORCH_REWORK_INFRA_RE` — content faults still count as rework.
- `reached_merge_tier()` detects when a ticket entered Story Acceptance / Merging / Docs / Done (or epic equivalents). `escalation_park_target()` calls it and returns `Blocked` for finished work, `Needs PO Decision` for everything else. Both `escalate_rework` and `block_for_iteration_cap` use `escalation_park_target`.
- `ORCH_REWORK_INFRA_RE` is documented in `docs/sop/ORCHESTRATOR_SOP.md` (knob-doc-drift green, 4/4).
- ADR-A-0018 now lists per-class effects explicitly: `environment-denial → cross-visit auto-park`, `transient → budget-neutral for both counters`, `logic → ticket-owned rework path`.

**Test evidence**: `PILOT-69-taxonomy-effects.sh` 4/4 — three distinct scenarios (functional bounce counted, transient abort skipped, mis-report counted); `reached_merge_tier` true/false cases.

### AC2 — ADR-A-0024 advisory counted with measurable promotion criterion and cadence

**PASS**

- `scripts/skill-mining.sh` counts `INTENT-HANDOFF-CLAIM-NOHASH` as a distinct per-role field (`r.nohash`), not folded into the `nomove` defect signal.
- Run-level total reported in the report header: `HANDOFF-CLAIM-NOHASH advisories (run total, ADR-A-0024 f promotion measure): N`.
- ADR-A-0024 (f) promotion criterion is now measurable: promote only if, over one full release, committing-seat advisories form a non-trivial majority of the run total (the false-positive class is review/PO/QAS seats, structurally identified).
- Cadence: evaluated at each release retrospective (a named retro step, not "someday"); a missing telemetry release records "not-evaluated", never a silent skip.

**Test evidence**: `test-skill-mining.sh` Test 8 — 34/34; asserts run-total line, per-role counts (be-developer=2, qas=1), and advisory NOT folded into nomove.

### AC3 — Rule for new taxonomies: a classification without a named effect is incomplete

**PASS**

- `docs/sop/ADR_AUTHORING_GUIDE.md` has a new section "Every Classification Must Name Its Effect (PILOT-69)" with an authoring checklist.
- `docs/rule-ledger.yaml` carries `R-1101` (kind: `unenforced`, with a risk note explaining why a mechanical sensor cannot enforce it across arbitrary taxonomies — valid rationale).
- `R-1101` follows `R-1100`; no id collision (`test-adr-id-uniqueness` 8/8 PASS).

---

## Full Test Run Summary

| Stage / Suite | Result | Count | Notes |
|---|---|---|---|
| `bash -n` orchestrator.sh | PASS | — | Syntax clean |
| `bash -n` skill-mining.sh | PASS | — | Syntax clean |
| `staged-suite --stage stories` | PASS | 52/52 | Includes PILOT-69-taxonomy-effects.sh 4/4 |
| `staged-suite --stage orch-core` | PASS | 726/726 | Full orchestrator scenario suite |
| `staged-suite --stage pool` | See note | 2 failures | Both pre-existing on merge-base (below) |
| `test-skill-mining.sh` | PASS | 34/34 | Includes new Test 8 (AC2 telemetry) |
| `test-orch-knob-drift.sh` | PASS | 4/4 | New knob documented |
| `test-adr-id-uniqueness.sh` | PASS | 8/8 | No ADR id collision |

### Pre-existing pool failures (confirmed on merge-base `cc1ea37e`)

| Test | Base result | Branch result | Classification |
|---|---|---|---|
| `test-rule-ledger.sh` | 18/19 (tdm.md C4 headings unregistered) | 18/19 (same) | Pre-existing, not a regression |
| `test-adr-reference-lint.sh` | Fails in pool `-P4` parallel run | Fails in pool `-P4` parallel run | Pre-existing parallel collision (passes in isolation: 6/6) |

Branch pool failures (2) are a strict subset of merge-base pool failures (3). PILOT-69 introduces no new test regressions.

---

## DoD / Evidence Checklist

- [x] AC1 — `rework_count()` transient exclusion verified in code + 4/4 targeted tests
- [x] AC1 — `escalation_park_target()` + `reached_merge_tier()` wired into both escalation paths
- [x] AC2 — `skill-mining.sh` NOHASH telemetry verified in code + 4 new skill-mining assertions
- [x] AC2 — ADR-A-0024 (f) criterion measurable with release-retro cadence
- [x] AC3 — R-1101 in rule-ledger.yaml (unenforced + risk note), ADR_AUTHORING_GUIDE section present
- [x] `ORCH_REWORK_INFRA_RE` documented in ORCHESTRATOR_SOP.md (knob-doc-drift green)
- [x] ADR-A-0018 per-class effects documented
- [x] No ADR id collision (R-1101 follows R-1100)
- [x] No harness/mirror drift (arch-reviewer confirmed, orch-core 726/726 green)
- [x] Merge readiness: `clean` (from ticket)
- [x] No design flag → exit target is Story Acceptance

**Verdict: APPROVED — all AC/DoD criteria met, no regressions introduced.**
