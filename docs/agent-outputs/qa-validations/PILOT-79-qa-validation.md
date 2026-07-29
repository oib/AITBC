# QA Validation — PILOT-79

**Ticket**: Ticket-Tag in Commits ist Pflicht ohne Guard — Bisect-Recovery faellt in einen Sackgassen-Status
**Branch**: PILOT-79-auto
**HEAD at test run**: `27d9e7db9867f8d86185f5207cf2bbcc57532bc0`
**QAS run date**: 2026-07-27
**Verdict**: APPROVED

---

## Test run (at HEAD 27d9e7db)

```
bash tests/test-commit-tag-guard.sh
  Total:  25
  Passed: 25
ALL PASS
```

Sibling guard (regression):
```
bash tests/test-local-main-guard.sh
  Total:  31  Passed: 31  Failed: 0
ALL TESTS PASSED
```

Knob-drift (forward-fix 27d9e7db):
```
bash tests/test-orch-knob-drift.sh
  Total:  4
  Passed: 4
ALL TESTS PASSED
```

Harness-mirror parity:
```
bash scripts/generate-governor.sh --providers --check
generate-governor.sh --providers --check: OK (agent_providers/claude_code == generated(harness/claude)).
```

Rule-ledger (ABS-285 baseline check):
```
bash tests/test-rule-ledger.sh   # at HEAD: 18/19
bash tests/test-rule-ledger.sh   # at base 7ef6f762: 18/19
```
The 18/19 failure is `docs/sop/rte-reference.md` headings without ledger rows, introduced by
PILOT-76 commit `608f03e0`. PILOT-79 never touches `rte-reference.md`. Zero regression from
this story.

---

## AC verification (all five, independently verified)

### AC1 — Guard checks story-branch messages, fails on missing tag

`scripts/commit-tag-guard.sh check-msg` classifies messages via `_verdict_of()`.
`scripts/hooks/commit-msg-ticket-tag-guard.sh` calls it for every seat commit on a
`<ticket>-auto` branch and exits 1 when the verdict is `untagged`.
Test `"untagged story commit FAILS (AC4)"` passes via a real `git commit` through the
installed hook in an isolated temp repo.
`docs(sop): update worktree section for PILOT-66` (the real 4d70ec09 bug) returns `untagged`
because `[PILOT-66]` appears only in prose; the regex `\[[A-Z][A-Z0-9]*-[0-9]+\]` requires
brackets. **PASS**

### AC2 — Exempt class explicit, documented, and tested

Two exempt paths in `_is_exempt()`:
- Subject matches `chore(release*` or `chore(governor*` → `exempt release-automation`
- Message body contains `[no-ticket]` → `exempt no-ticket-marker`

Both exercised in tests (assertions 5 and 6 of the AC1/AC2 block).
CONTRIBUTING.md "Exempt commits" section (commit `d6241f5f`) carries a two-class table with
explicit `[no-ticket]` guidance. The exempt logic lives in `commit-tag-guard.sh`, not buried
in the hook. **PASS**

### AC3 — Guard runs before story merges to epic branch

The hook is `commit-msg` (not `pre-push`). It fires at commit time on the story branch,
before that branch merges into `epic/*`. Branch detection (`ORCH_GUARD_BRANCH` or
`git symbolic-ref --short HEAD`) skips `main`, `master`, and `epic/*` explicitly:

```bash
case "$branch" in
    epic/*) exit 0 ;;
esac
```

Tests confirm: `seat on epic/* -> allowed (integration territory)` PASS, `seat on main -> allowed` PASS.
`provision_ticket_tag_guard` in `orchestrator.sh` installs the hook at startup, right after
`provision_main_head_guard`, before the event loop. **PASS**

### AC4 — Regression test with both cases

Three end-to-end assertions via a real `git commit` through the installed hook in a scratch repo:

| Case | Result |
|------|--------|
| `feat(api): tagged work [PILOT-79]` on story branch | PASS (exit 0) |
| `feat(api): untagged work` on story branch | FAIL (exit 1) |
| `chore(release): promote governor to v9.9.9` on story branch | PASS (exit 0) |

Kill switch `ORCH_TICKET_TAG_GUARD=0` assertion also passes. **PASS**

### AC5 — Bisect recovery: no rewrite, no dead-end Needs PO Decision

`commit-tag-guard.sh recover <range> <culprit-sha>` in commit `d55319c5` implements a
three-step fallback:
1. culprit itself tagged → `child=ID via=self` (exit 0)
2. nearest tagged commit in `culprit..bad` (reverse ancestry) → `child=ID via=next-tagged sha=SHA` (exit 0)
3. first merge commit in `culprit..bad` carrying a tag → `child=ID via=merge sha=SHA` (exit 0)
4. nothing found → `unresolved` (exit 3)

Tests confirm (AC5 block):
- Untagged culprit with tagged successor → resolves to `child=PILOT-91 via=next-tagged` (exit 0)
- Wholly-untagged range → `unresolved` (exit 3)

`harness/claude/agents/rte.md` step 6 runs `commit-tag-guard.sh recover` before any `Needs
PO Decision` transition. `Needs PO Decision` is the `else` branch (exit 3 only).
Provider mirror regenerated in commit `d55319c5`; `--providers --check` confirms parity.
Old commits not rewritten. **PASS**

---

## Summary

| Criterion | Result |
|-----------|--------|
| AC1: guard blocks untagged story commits | PASS |
| AC2: exempt class documented and tested | PASS |
| AC3: guard fires before story→epic merge | PASS |
| AC4: regression, both cases | PASS |
| AC5: bisect recovery, no dead-end | PASS |
| Sibling guard regression (test-local-main-guard.sh 31/31) | PASS |
| Knob-drift guard (test-orch-knob-drift.sh 4/4) | PASS |
| Harness-mirror parity (--providers --check) | PASS |
| Rule-ledger 18/19: PILOT-76 debt, ABS-285 baseline-confirmed | NON-REGRESSION |

**Verdict: APPROVED — releasing to Story Acceptance.**
