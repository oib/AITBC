# QA Validation — ABS-601
**Commit under review**: `0b491700` (rebased onto epic tip `90489abc`)
**Branch**: `ABS-601-auto`
**Verdict**: **APPROVED**
**Date**: 2026-07-27

> **Re-validation note**: This supersedes the prior QAS run at `882ce1af`. The branch was
> rebased onto the ABS-600 epic tip (`90489abc`) during the Merging lane; system-architect
> confirmed no content change and all 5 ACs intact (handoff 2026-07-27T21:28Z). This seat
> re-ran all three suite stages at the new HEAD before approving.

---

## AC Validation

| AC | Description | Result |
|----|-------------|--------|
| AC1 | `_common-rules.md` §5 forbids ending a turn waiting on an async completion signal; names the one-shot `claude -p` reason and both Pilot 8 incident phrases | ✅ PASS |
| AC2 | `rte.md` Epic-Integration station directs long work to `tests/staged-suite.sh` (path relative to target repo), warns explicitly against backgrounding, names `ASYNC-WAIT-STALL` | ✅ PASS |
| AC3 | `handoff_awaits_async_completion()` matches both verbatim incident phrases; a finished-run report (`"staged suite passed"`) does NOT match | ✅ PASS |
| AC4 | `record_nomove` routes async-wait handoffs to `record_async_wait_stall` → `INTENT-ASYNC-WAIT-STALL` in run.log, escalates to Needs PO Decision; plain no-moves still record `HANDOFF-NOMOVE` (no masking) | ✅ PASS |
| AC5 | Spawn runs in its own process group (`set -m`); `pkill -TERM/KILL -g "$spawn_pid"` reaps any orphaned children at spawn end; `SPAWN-REAP` logged in run.log | ✅ PASS |

---

## Suite Results at HEAD `0b491700`

All three stages run synchronously in this seat (staged-suite.sh --stage, one at a time).

| Stage | Result | Count | Duration |
|-------|--------|-------|----------|
| `stories` | ✅ PASS | 61/61 | 247s |
| `orch-core` | ✅ PASS | 755/755 | 242s |
| `pool` | ✅ PASS | 108/108 | 439s |

`staged-suite.sh --verify` → **GATE GREEN** (all 3 stages recorded at HEAD `0b4917005c2d`).

**Count deltas vs. prior run at `882ce1af`**: stories +1 (ABS-601-async-wait-stall.sh now
counted separately), orch-core +14 (the 14 new asserts inside that include), pool 18/19 → 108/108
(the `f1449aa8` knob-documentation commit also fixed the pre-existing `test-rule-ledger.sh`
failure that the prior run had to accept as pre-existing).

---

## Sensors

- `scripts/orch-knob-doc-drift.sh` → **exit 0** (`ORCH_ASYNC_WAIT_SENSOR` and `ORCH_REAP_SPAWN_CHILDREN` documented in `docs/sop/ORCHESTRATOR_SOP.md`)
- `tests/test-agent-prompt-size-budget.sh` → **19/19 PASS**
- `scripts/generate-governor.sh --providers --check` → **OK** (mirror parity, Common Rule 10)

---

## History (brief)

| Iteration | Commit | Verdict | Issue |
|-----------|--------|---------|-------|
| 1 | `8a26069c` | BLOCKED | undocumented knobs + ratchet under-counted |
| 2 | `882ce1af` | APPROVED | knobs added, ratchet raised to 16 |
| 3 (this) | `0b491700` | APPROVED | clean rebase onto `90489abc`; full suite green including pool |

---

## Verdict

**APPROVED** — all 5 ACs met, all 3 suite stages green (924/924 asserts), all sensors clean
at HEAD `0b491700` pushed to `gitlab/ABS-601-auto`.
