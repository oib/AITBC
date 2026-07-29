# QA Validation Report — ABS-272

**Ticket**: ABS-272 — Seats teilen sich eine refs/stash über alle Worktrees (Rezept + Riegel)
**Branch**: ABS-272-auto
**HEAD**: 28444fe (fix commit) on top of 41f8402 (implementation commit)
**Validator**: QAS (independent verification)
**Date**: 2026-07-14
**Verdict**: ✅ APPROVED

---

## Summary

ABS-272 closes a live, repeatedly-occurring data-loss bug: `git stash` writes to a
single `refs/stash` that ALL worktrees of a repo share, while the runner operates seats
concurrently in per-ticket worktrees. A seat stashing for a baseline comparison can pop
a *sibling* seat's stash and silently eat its uncommitted work (4 confirmed incidents;
a 5th occurred live during the architecture review).

The implementation delivers: (a) a codified stash-free recipe in the shared seat rules
(`_common-rules.md` §9), and (b) a two-layer mechanical deny (settings deny rule +
PreToolUse hook) — exactly the #PATH_DECISION approach specified in the ticket.

The Iteration 1 blocking defect (`origin/main` hardcoded in a token-substituted file)
was fixed in commit `28444fe` using the correct `main` token.

---

## Acceptance Criteria Verification

### AC1 — Codified rule in `harness/claude/agents/_common-rules.md` §9

**Status: ✅ PASS**

Static analysis of `harness/claude/agents/_common-rules.md`:

| Check | Result |
|-------|--------|
| `git stash` declared FORBIDDEN | ✅ Line 143: `` `git stash` is FORBIDDEN in your worktree `` |
| Reason states shared `refs/stash` | ✅ Line 144: `` `refs/stash` is ONE stack that ALL worktrees of the repo SHARE `` |
| Recipe contains `git worktree add --detach` | ✅ Line 158 (copyable bash block) |
| Recipe bash block contains no `git stash` command | ✅ Verified: bash block has no `git stash` |
| Recipe uses `main` token (consumer-portable) | ✅ Line 156: `origin/main` |
| No hardcoded `origin/main` anywhere in file | ✅ grep clean — blocking defect from Iteration 1 confirmed fixed |

The Iteration 1 blocking defect (`origin/main` hardcoded in a token-substituted file)
is confirmed fixed in commit `28444fe`. Token matches the sibling precedent at `rte.md:110`.

Test suite assertions (all PASS):
- `ABS-272 AC1: _common-rules.md carries the stash-free baseline recipe`
- `ABS-272 AC1: the rule states the reason (shared refs/stash across worktrees)`
- `ABS-272 AC1: the codified recipe contains no git stash`
- `ABS-272 AC1: the recipe's base branch uses the main token (consumer-portable)`
- `ABS-272 AC1: the recipe does not hardcode origin/main (breaks non-main consumers)`

---

### AC2 — Mechanical deny rule on the generated seat permission surface

**Status: ✅ PASS**

**Layer A: settings deny rule injected by `merge_deny_rules()` in `orchestrator.sh`:**
- `ORCH_WORKTREE_DENY="Bash(git stash:*)"` set at `orchestrator.sh:404`
- `merge_deny_rules()` performs jq set-union, idempotent, worktree-only
- `merge_deny_rules "$dst" "worktree provisioning"` called at line 3944
- Kill switch: `ORCH_STASH_GUARD=0` skips injection (ABS-111 pattern)
- Confirmed in `settings.template.json` (both harness and provider mirror identical — ADR-A-0015)

**Layer B: PreToolUse hook `pre-bash-stash-guard.sh` — driven end-to-end:**

| Test case | Expected | Actual |
|-----------|----------|--------|
| `git stash` (seat context) | exit 2 | ✅ BLOCKED |
| `git stash pop` (seat context) | exit 2 | ✅ BLOCKED |
| `git stash push -u` (seat context) | exit 2 | ✅ BLOCKED |
| `git stash save wip` (seat context) | exit 2 | ✅ BLOCKED |
| `git stash apply` (seat context) | exit 2 | ✅ BLOCKED |
| `git stash drop` (seat context) | exit 2 | ✅ BLOCKED |
| `git stash clear` (seat context) | exit 2 | ✅ BLOCKED |
| `cd /tmp && git stash pop` | exit 2 | ✅ BLOCKED (global flag normalization) |
| `git -C /tmp/wt stash pop` | exit 2 | ✅ BLOCKED (global flag normalization) |
| Refusal message contains stash-free recipe | present | ✅ `git worktree add --detach` found |
| Refusal message states reason | present | ✅ `SHARED by ALL worktrees` found |
| Blocked command logged to `ORCH_STASH_GUARD_LOG` | BLOCKED log entry | ✅ confirmed |
| `git stash list` (read-only) | exit 0 | ✅ ALLOWED |
| `git stash show -p` (read-only) | exit 0 | ✅ ALLOWED |
| `git commit -m 'stash the idea'` (false-positive) | exit 0 | ✅ ALLOWED |
| `git status` (false-positive) | exit 0 | ✅ ALLOWED |
| Human shell (`env -i`, no seat markers) | exit 0 | ✅ ALLOWED |
| `ORCH_STASH_GUARD=0` kill switch | exit 0 | ✅ ALLOWED |

Hook registered as `PreToolUse`/`Bash` matcher in `harness/claude/hooks-config.json` (line 52).
`ORCH_STASH_GUARD` exported from `orchestrator-spawn-claude.sh:156`.
ADR-A-0015 mirror parity: `harness/claude/hooks/pre-bash-stash-guard.sh` ==
`agent_providers/claude_code/hooks/pre-bash-stash-guard.sh` — diff clean.

---

### AC3 — Non-regression proof via stash-free recipe

**Status: ✅ PASS**

QAS independently drove the §9 recipe in an isolated test repo with a sibling seat's
work already on the shared stash stack (reproducing the exact incident scenario):

| Assertion | Result |
|-----------|--------|
| Shared stash stack byte-identical after recipe (sibling's work untouched) | ✅ PASS |
| Own uncommitted work survives the baseline run | ✅ PASS |
| Throwaway baseline worktree shows the base state (not the branch state) | ✅ PASS |
| Worktree count unchanged (no worktree leak) | ✅ PASS |
| No throwaway worktree directory remains | ✅ PASS |

Test suite (all PASS):
- `ABS-272: the throwaway worktree really shows the BASE state`
- `ABS-272: the seat's OWN uncommitted work survives the baseline run`
- `ABS-272: the SHARED stash stack is unchanged (sibling's work untouched)`
- `ABS-272: the throwaway worktree is removed (no worktree leak)`
- `ABS-272: recipe leaves no directory behind`

---

### AC4 — Full suite: no new failing test names (established via stash-free recipe)

**Status: ✅ PASS**

QAS ran `bash tests/test-orchestrator.sh` independently on the branch (using the §9
stash-free recipe for context — no stash used). Results:

| Metric | QAS Branch Run |
|--------|---------------|
| Total assertions | **740** |
| PASS | **718** |
| FAIL | **22** |
| ABS-272 assertions | **32/32 PASS, 0 fail** |
| ABS-272 assertions in failing list | **0** |

The 22 failures are **all pre-existing, environment-dependent** — not introduced by this
branch. Full list (confirmed — none are ABS-272):

- Provenance assertions (harness != script repo; stable-governed checkout)
- DEMO-1/Backlog label gating tests (neutral-profile env)
- Follow-up budget tests (DEMO-1 env)
- Model-label tests (DEMO-1/DEMO-3/DEMO-7 env)
- AC1-AC3 label-propagation tests (env)

These 22 failures reproduced at `f7c9a68` (confirmed by the architecture reviewer in the
Iteration 1 gate-results comment), making the failing-NAME diff empty.

---

## Additional Hygiene Checks

| Check | Result |
|-------|--------|
| `_common-rules.md` §9 uses `main` token | ✅ |
| No `origin/main` literal in `_common-rules.md` | ✅ |
| Hook refusal message is branch-neutral | ✅ (`origin/<your-main-branch>`) |
| `merge_deny_rules()` mirrors `merge_allow_grants` shape (jq set-union, idempotent) | ✅ |
| Worktree-only scoping (operator's main checkout unaffected) | ✅ |
| `ORCH_STASH_GUARD` exported by spawn seam | ✅ (`orchestrator-spawn-claude.sh:156`) |
| Hook marks `ABS-272-stash-guard` token for test grep | ✅ (hook line 5) |
| ADR-A-0015 provider mirror parity (harness == agent_providers diff clean) | ✅ |
| Shared stash stack left untouched (10 entries, out of scope) | ✅ |
| No throwaway worktrees leaked from dev/review sessions | ✅ |

---

## Failure Classification

All 22 suite failures are classified as **`environment`** — the provenance check expects
`harness == script repo`, which cannot hold in a stable-governed checkout. These are
not routed to the implementer (environment failures per QAS routing table).

**Zero `code` failures introduced by this branch.**

---

## Verdict

**✅ APPROVED — all 4 ACs met and independently evidenced**

| AC | Status | Key evidence |
|----|--------|-------------|
| AC1 | ✅ PASS | §9 rule present, reason stated, recipe correct, `main` token — 5/5 test assertions PASS |
| AC2 | ✅ PASS | Two-layer mechanical deny confirmed end-to-end — 18/18 hook scenarios PASS, deny rule injected, kill switch works |
| AC3 | ✅ PASS | Non-regression: stash stack byte-identical, no worktree leak — 5/5 recipe assertions PASS |
| AC4 | ✅ PASS | 740 assertions, 718 PASS, 22 pre-existing env failures; 32/32 ABS-272 assertions PASS, failing-name diff empty |

No `design` flag on ticket → exit target is **Story Acceptance**.
