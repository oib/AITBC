# QA Validation Report — ABS-218

**Date**: 2026-07-12  
**Reviewer**: qas  
**Branch**: ABS-218-auto  
**HEAD**: dd3cf44 (fix(tests): commit gitignored skill-mining run.log fixture [ABS-218])  
**Status**: APPROVED (Iteration 2 of 3 — rework re-validation)  

---

## Context

First QAS pass (6a7403b) approved the suite at 28/28 from a working-tree run. po-agent rejected at Story Acceptance: committed state scored 25/28 because `tests/fixtures/skill-mining/state/run.log` was matched by `.gitignore:52` (`*.log`) and never committed. Three assertions failed (AC3 NOMOVE path, AC4 proposal count, AC6 fixture completeness).

Fix `dd3cf44`: targeted `.gitignore` negation (`!tests/fixtures/skill-mining/state/run.log`) + committed fixture. No change to `skill-mining.sh` or test logic.

This pass re-validates from **committed state only** using the PO's clean-checkout method.

---

## Validation from Committed State (`git archive HEAD`)

```bash
git archive HEAD | tar -x -C $CLEAN_DIR
bash $CLEAN_DIR/tests/test-skill-mining.sh
# → Total: 28, Pass: 28, Fail: 0, Exit: 0
```

Root-cause fix confirmed:

```
git check-ignore -v tests/fixtures/skill-mining/state/run.log
# → "NOT ignored (tracked)"

git ls-tree HEAD tests/fixtures/skill-mining/state/run.log
# → 100644 blob 088863b… tests/fixtures/skill-mining/state/run.log (271 B)

.gitignore:58-59: negation present
  # Test fixtures committed on purpose (skill-mining miner source #2)
  !tests/fixtures/skill-mining/state/run.log
```

---

## AC Validation

### AC1 — bash/python3-stdlib; no foreign deps; Markdown per role; graceful degradation

**PASS** — unchanged from first pass; confirmed again in Test 0 + Test 5 (28/28 run).

### AC2 — Per-role fields: seats, calls median/max vs turn-ceiling, help, NOMOVE/RESPAWN/CRASH, Skill-calls/seat, top normalized commands

**PASS** — Test 1 (6 assertions, all PASS) from committed state.

### AC3 — Threshold verdict SKILL-KANDIDAT / OK; three paths; thresholds env-overridable

**PASS** (was FAIL at 6a7403b — now fixed)

| Role | Trigger path | Verdict |
|------|-------------|---------|
| `be-developer` | pattern 12x / 3 seats (≥10x/3) | SKILL-KANDIDAT |
| `system-architect` | help invocations 3 (≥3) | SKILL-KANDIDAT |
| `bsa` | NOMOVE+RESPAWN 2 (≥2) | SKILL-KANDIDAT ← previously missed |
| `qas` | below all thresholds | OK |

`bsa is a candidate (NOMOVE path)` and `bsa verdict cites NOMOVE+RESPAWN>=2` both PASS from committed state.

### AC4 — `--proposals` writes one ABS-4-shaped skeleton per candidate; OK role gets none

**PASS** (was FAIL at 6a7403b — now fixed)

3 candidates → 3 proposal files; qas (OK) produces none. Test 4 (5 assertions, all PASS) from committed state.

### AC5 — Normalization + redaction; no secrets in report

**PASS** — re-verified non-vacuous after fixture change: `supersecret` absent, `<REDACTED>` present. Test 3 (4 assertions, all PASS).

### AC6 — Fixture-driven; no live access; read-only guard

**PASS** (was FAIL at 6a7403b — now fixed)

Fixture tree is self-contained in the repository. `run.log` present in `git archive` extract. Checksum guard PASS. Test 6 PASS from committed state.

---

## Scope Compliance

Only `dd3cf44` added: 2 files, 7 insertions — `.gitignore` negation + committed `run.log`. No change to `skill-mining.sh` or test logic. No product code modified.

---

## Final Verdict

**APPROVED** — All 6 AC criteria met from **committed state**. 28/28 fixture assertions pass via `git archive` clean-checkout run. `shellcheck -x` 0 findings on both files. Root cause of Story-Acceptance reject resolved.
