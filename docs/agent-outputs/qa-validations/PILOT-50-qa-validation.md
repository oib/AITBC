# QA Validation Report — PILOT-50

**Ticket**: PILOT-50 — Staged suite runner + HEAD-bound completeness ledger  
**Branch**: `PILOT-50-auto`  
**HEAD at validation**: `f02e9cefe5a8e8955162bb998b38b7f994e363d8`  
**Commits on branch**: `e68bc5bb` (feat), `f02e9cef` (docs/header fix)  
**QAS run date**: 2026-07-26  
**Validator**: qas seat  

---

## Scope

Files changed vs merge-base `2c564f20`:
- `tests/staged-suite.sh` — new staged runner + HEAD-bound ledger
- `tests/test-staged-suite.sh` — integrity/falsification test (10 assertions)
- `harness/claude/agents/qas.md` + `rte.md` — gate-seat role def updates (AC3)
- `agent_providers/claude_code/prompts/qas.md` + `rte.md` — provider mirror (ABS-317)
- `.gitignore` — `work/.suite-stage-ledger` entry added

---

## AC Validation

### AC1 — Deterministisch partitionierter Etappen-Einstieg ✅ PASS

Stage plan is FIXED BY THE SCRIPT (`staged-suite.sh`); a seat cannot alter which
files run. `--list` output:

```
Stage plan (HEAD f02e9cefe5a8) — partition is fixed by this script:
  orch-core  test-orchestrator.sh scenario blocks (no story includes), TEST_JOBS=4
  stories    tests/orchestrator.d/*.sh includes, fanned out one-process-per-file (-P4)
  pool       every other tests/test-*.sh, via run-all.sh (-P4)
```

Partition logic: `orch-core ∪ stories = full test-orchestrator.sh` (no overlap, no gap).
`pool = all other test-*.sh`. Coverage is total; no file can be omitted by seat choice.

### AC2 — Vollständigkeits-Nachweis (HEAD-bound ledger) ✅ PASS

`--verify` is green ONLY when every stage has a `pass` record at the CURRENT HEAD on
a CLEAN tree. Verified via:
- `test-staged-suite.sh` assertions (tests 2–6 exercise ledger logic): **10/10 PASS**
- Live ledger test: subset → `GATE RED`, full set → `GATE GREEN` (exit codes 1/0 confirmed)
- SHA-binding: passes at a fake SHA do not count; real HEAD requires fresh stage runs

### AC3 — Rollen-Definitionen beschreiben den Etappen-Aufruf ✅ PASS

Both `harness/claude/agents/qas.md` and `rte.md` updated:
- **QAS**: new bullet under "Validate always" instructs staged calling for suites
  exceeding the ~10-min call limit; references `staged-suite.sh --stage` + `--verify`.
- **RTE**: step 4 now has a full "Run the suite in STAGES" block with the
  `for s in … --stage "$s"` + `--verify` recipe.

Provider mirror (`agent_providers/claude_code/prompts/`) updated in lockstep;
`generate-governor.sh --providers --check` = **OK** (no drift).

### AC4 — Falsifikation: Teilmenge darf Gate NICHT passieren ✅ PASS

`test-staged-suite.sh` test "verify RED when a stage is SKIPPED (AC4)": **PASS**  
`test-staged-suite.sh` test "verify RED when a stage FAILED": **PASS**

Live confirmation: running alpha+beta but not gamma → `--verify` exits **1** with
`GATE RED: suite is NOT proven green at this HEAD. missing stages: gamma`.

### AC5 — Falsifikation 2: Jede Stage einzeln unter dem Aufruf-Limit ✅ PASS

All 3 stages measured independently on this machine (no parallel load):

| Stage     | Tests       | Wall-clock | Limit (600s) |
|-----------|-------------|------------|--------------|
| orch-core | 723/723 ✅  | **204s**   | ✅ <<600s    |
| stories   | 48/48 ✅    | **119s**   | ✅ <<600s    |
| pool      | 92/92 ✅    | **196s**   | ✅ <<600s    |

HEAD at measurement: `f02e9cefe5a8`. All stages PASS; each fits comfortably under
the 10-minute Bash-tool call limit with safety margin of 3×+ (204s vs 600s).

---

## Supplemental Checks

| Check | Result |
|---|---|
| `test-staged-suite.sh` (10 assertions, AC4 + ledger integrity) | **10/10 PASS** |
| Harness↔provider mirror parity (`--providers --check`) | **OK** |
| `SUITE_` prefix vars survive `unset "${!ORCH_@}"` scrub (ABS-285) | **Confirmed** |
| `.gitignore` entry for `work/.suite-stage-ledger` | **Present** (line 175) |
| Commits on PILOT-50-auto branch | `e68bc5bb`, `f02e9cef` — both reachable |
| Worktree branch at validation | `PILOT-50-auto` ✅ |

---

## Observations (non-blocking)

1. **Shared helper mechanic with `pre-release-check.sh`** (mentioned under VERWANDT/guardrails):
   `staged-suite.sh` implements its own self-contained ledger. The proposal for
   `pre-release-check.sh` is a separate future ticket. None of the 5 ACs require a
   shared helper in this ticket — noted for follow-up.
2. **Pre-existing flake in `test-adr-reference-lint.sh`** under `-P4` pool load (noted by
   system-architect as non-blocking carry-forward): not observed in my pool run (PASS), but
   the architect's observation warrants a follow-up ticket.

---

## Verdict

**✅ APPROVED — all 5 ACs PASS, all falsifications confirmed, mirror parity OK.**

Exit transition: → `Story Acceptance` (no `design` flag on ticket).
