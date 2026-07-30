---
name: _common-rules
description: Shared cross-seat rules prepended to every role body by the spawn seam (ABS-174). Not a spawnable role; the underscore prefix keeps it out of role resolution.
---

# Common Seat Rules (ABS-174)

These rules apply to every seat, regardless of role. The spawn seam
(build_agents_json in scripts/orchestrator-spawn-claude.sh) prepends this body,
frontmatter stripped, ahead of the role-specific prompt. They therefore live
here EXACTLY ONCE instead of being copied into every agent definition. Each role
definition keeps only a short distillate of these rules so that interactive
Task-tool use (which does not pass through the spawn seam) loses nothing
essential.

## 1. Evidence-Disziplin (handoff truthfulness, ABS-137)

Before you write your handoff, re-validate the ACTUAL end state; never report
from intention or memory:

- Repository work: run `git status --short`, `git log --oneline -1`, and confirm
  the push landed.
- Tracker work: confirm the comment posted and the transition actually applied.

The handoff MUST describe the verified end state. Never write "changes staged
but not committed" or "commit pending" when the commit exists, nor "comment
posted" or "transition done" when it did not happen (Befund 9, run ABS-126).

**If you created commits, you MUST name their hashes on a `commits:` line in your
handoff record (ABS-255, ADR-A-0024).** You already run `git log --oneline -1`;
this only makes that evidence machine-readable:

```markdown
## Handoff

- role: <role>
- ticket: <ticket-id>
- commits: <sha> [<sha> ...]   # REQUIRED when this spawn created commits; OMIT when it created none
- summary: ...
- status: ...
- next: ...
```

**The runner VERIFIES every hash you name, before it accepts your handoff.** Each
one is checked for existence (`git cat-file -e <sha>^{commit}`) and reachability
(`git for-each-ref --contains <sha>` — at least one ref must contain it). A hash
that does not exist, or a commit that no ref contains (committed on a detached
HEAD, or on a branch since discarded), is a **mis-report**: your handoff is
REFUSED, the declared transition is not applied, any self-transition is undone,
and the ticket bounces back to you to actually commit the work. Repeated
mis-reports escalate to `Needs PO Decision` via the existing rework/no-move
budget. Claiming a commit you did not land is therefore strictly worse than
honestly reporting that you did not commit — report the truth (lineage: a seat
claimed a reconciliation twice that `git log -S` proved no ref ever contained,
and the next seat echoed the claim).

**A FORWARD transition that claims work COMPLETE additionally requires the commit
to be PUSHED (PILOT-75/ABS-581).** When your handoff moves the ticket to `In
Review` or any later station, the runner checks each claimed commit against the
ACTIVE remote (`git for-each-ref --contains <sha> refs/remotes/<active-remote>/`)
— not merely a local ref. A commit that exists only in your worktree LIES about
the state of the remote: outside the worktree it does not exist and vanishes when
the worktree is cleaned up (four incidents across three runs — the operator had
to recover the commits by hand). So COMMIT **and** PUSH to the active remote
before you transition forward; a never-pushed commit is refused on the same
mis-report path. The active remote is the only source (ADR-A-0030) — the runner
resolves it from the pin, never a hardcoded `origin`. This applies to every seat,
including main-checkout seats (docs/PO/RTE): uncommitted or unpushed work in the
main checkout is a fault state, not an intermediate one.

## 2. Commit-Format

- Atomic commits in SAFe format: `type(scope): description [AITBC-XXX]`
  (for example `feat(api): add subscription webhook [AITBC-123]`).
- One logical change per commit; you own, and create, your own commits.
- Do not create PRs or merge unless your role explicitly owns that step.

## 3. Session-Resume-Etikette

- On a resumed spawn, treat prior context as a CLAIM, not ground truth:
  re-verify the real repository and tracker state before acting.
- Never redo work that already landed, and never assume incomplete work finished.
- Continue from the verified state; if it contradicts the prior handoff, trust
  the verified state and say so.

## 4. Tracker-Protokoll

- Use the tracker adapter handed to you (the tracker_cmd / TRACKER_CMD in your
  spawn packet) for ALL tracker operations, not an example adapter copied from an
  agent definition.
- For the CLI surface (get / search / comment / transition / link and the
  mandatory `--body-file` / `--expect-from` flags), invoke the `tracker-ops`
  skill — a copy-paste quick reference. **Do NOT run `$TRACKER_CMD help`** to
  relearn the CLI.
- Posting your gate-results or decision comment AND performing your exit
  transition are YOUR duty; the runner does not transition for you.
- Record evidence on the ticket before handing off (ADR-A-0006 active tracking).

## 5. Background-Task-Disziplin (spawn lifecycle, ABS-195)

Never end your spawn while a background task you started is still running. If you
launch a long-running task in the background (test suite, build, migration,
`run_in_background`, a `&`-detached job), you MUST wait for it synchronously OR
collect its result — exit status and output — BEFORE you write your final
handoff. An interim "kicked off the tests, will report later" message is NOT a
valid final message: once your `claude` process ends the task's result is lost
and the ticket is left orphaned in its in-progress status with no owning seat
(ABS-195, ABS-151 Iteration-5-Befund). Await the task, read its result, then hand
off with the verified outcome. If you truly cannot wait, do not background the
task — run it in the foreground so the process cannot end before it finishes.

**Your spawn is a ONE-SHOT invocation — there is NO later turn and NO surviving
event loop for a completion notification to arrive in (ABS-601).** A spawned seat
runs as a single non-interactive `claude -p` call: when your turn ends, the
process ends. So NEVER end your turn waiting on an ASYNCHRONOUS completion signal —
"I'll wait for the background task completion notification before proceeding" or
"let me keep checking until it completes" — that notification structurally CANNOT
come, because nothing outlives your turn to receive it. Both times this happened
the runner read the seat's `subtype=success` exit as a clean run when the seat had
done NOTHING, and an epic-integration failed for the fifth time (Pilot 8). Run
long-running work SYNCHRONOUSLY instead: a single BLOCKING call with a sufficient
timeout, or — for the full test suite at a gate — the staged runner
`tests/staged-suite.sh` (path relative to the target repo, ABS-599), whose
per-stage calls each block to completion under the 10-minute tool cap. A runner
sensor now NAMES this failure (`ASYNC-WAIT-STALL`) instead of accepting it as
success, and reaps any background process you leave behind when your spawn ends.

## 6. Branch-Disziplin (never commit to local main, ABS-224)

ALL your work lands on the STORY branch / your provisioned worktree — NEVER on
the local `main` (or `master`) of the main checkout. This includes every
artefact, not just source: a QA-validation report, a docs update, or any
generated file goes on the SAME story branch that carries the work (e.g.
`<TICKET>-auto`), so it travels into that story's PR and reaches origin. A commit
on the local main reaches NO PR and never origin — it is silently lost and
poisons the branch base for every future branch off main (Watch-Run v2.24.0:
QAS reports committed to local main, dc8449f/cccfbd5, in no PR). A mechanical
pre-commit guard enforces this (ABS-224); do not try to work around it — if you
find yourself on `main`, switch to the story branch/worktree instead.

## 7. Claim-Protokoll (pull the ticket at work start, ABS-224 AC6)

Implementer seats transition the ticket to "In Progress" IMMEDIATELY at the
start of work — BEFORE touching the first file — so the board reflects that the
ticket is actively being worked. Leaving a ticket in "Ready for Development"
while you edit in a worktree makes the board show calm where there is work
(ABS-213 Befund: >45 min of worktree edits with the ticket still at "Ready for
Development"). The status chain stays seat-led: you own the transition, the
runner does not do it for you. The reconcile sweep only WARNS on a skipped claim
(it never auto-transitions), so the pull is your responsibility.

## 8. Kill-Scope (never kill by name/pattern, ABS-243)

Kill ONLY processes YOU started, and ONLY by a PID you remember or by your own
process group/session — NEVER by name/pattern. A name-pattern kill matches every
process whose command line carries the pattern, including processes outside your
spawn tree: a seat that ran `pkill -9 -f "scripts/orchestrator.sh --live"` reaped
the operator's LIVE watch-orchestrator TWICE (2026-07-12, session a33f54f8). That
is the exact incident this rule closes.

- ALLOWED (PID-/group-/session-scoped): `kill "$pid"`, `kill -TERM "$pid"`,
  `kill -0 "$pid"`, `pkill -P "$pid"` (children of a PID you started),
  `pkill -g "$pgid"` / `pkill -s "$sid"` (your own process group / session).
- FORBIDDEN (name/pattern): `pkill -f …`, `pkill <name>`, `killall …`,
  `kill $(pgrep -f …)` / `pgrep -f … | xargs kill`, and any `ps … | grep … `
  name lookup piped into a kill (ABS-244).
- FORBIDDEN (broadcast): `kill -9 -1` / `kill -- -1` — a `-1` TARGET signals
  EVERY process you own, the operator's orchestrator included (ABS-244).
  (`kill -1 "$pid"` is fine: there `-1` is the SIGNAL, sent to one PID.)

A mechanical PreToolUse guard enforces this for seats (ABS-243/ABS-244); do not
try to work around it. If you must clean up, target a PID you captured when you
started the process. Kill switch (operator only): `ORCH_KILL_GUARD=0`.

**The guard is a guardrail, not a cage — the rule above binds you where the guard
cannot.** It is a string matcher on the command line, so obfuscation (base64/eval,
a wrapper script, `python -c "os.kill(…)"`) slips past it by design, and you run
as the operator's own UID with write access to the guard file itself. Evading it
by any of those routes is a governance violation, not a clever workaround
(rationale + full vector matrix: `docs/security/ABS-244-kill-guard-bypassability-review.md`).

## 9. Baseline-Vergleich ohne Stash (never `git stash`, ABS-272)

`git stash` is FORBIDDEN in your worktree — `git stash`, `git stash push/save`,
`git stash pop/apply/drop/clear`. Reason: **`refs/stash` is ONE stack that ALL
worktrees of the repo SHARE** (only `HEAD`, `refs/bisect`, `refs/worktree` and
`refs/rewritten` are per-worktree). Sibling seats run CONCURRENTLY in their own
worktrees, so your `git stash pop` pops whatever landed on the shared stack last —
possibly a sibling's stash — and silently eats their uncommitted work (three
incidents on 2026-07-13: ABS-251 popped ABS-255's stash, ABS-254 popped ABS-265's).

The baseline comparison itself stays MANDATORY — only its vehicle changes. Use a
throwaway worktree on the base commit: it needs no stash, and your own working tree
is never touched.

```bash
base=$(git merge-base HEAD origin/main)   # the commit your work branched from
wt=$(mktemp -d)/base
git worktree add --detach "$wt" "$base"   # base state, isolated from your tree
( cd "$wt" && bash tests/test-orchestrator.sh )   # <- baseline result (your suite)
git worktree remove --force "$wt"         # ALWAYS clean up (no worktree leak)
```

Compare the baseline's failing-test NAMES against your branch's run; only NEW names
are your regressions. To park work in progress, COMMIT it on your story branch (you
own your commits) — never stash it. Read-only `git stash list` / `git stash show`
stay allowed.

**Measure both sides in the SAME window and with the SAME env (ABS-285).** A test
result is only a function of the commit if the environment is held fixed. Seats export
~37 `ORCH_*` vars, and some leak into the code under test (`ORCH_TOOLS` and
`ORCH_OVERRIDES_DIR` each flipped assertions in `tests/test-agent-def-overlay.sh`), so
a baseline measured by seat A is NOT comparable to a branch run by seat B, nor to a
baseline someone recorded yesterday. Therefore:

- Run baseline and branch **back-to-back, from the same shell**, as the block above does.
- **Never trust a baseline number from a ticket, a comment, or an earlier run** — re-measure it.
- If a test drives the spawn seam or the runner, it must scrub the ambient env itself
  (`unset "${!ORCH_@}"` — prefix-unset, not an enumerated list). `tests/orchestrator.d/ABS-285-env-scrub.sh`
  pins this mechanically.

A mechanical PreToolUse guard plus a `permissions.deny` rule enforce this for seats
(ABS-272); do not try to work around them. Kill switch (operator only):
`ORCH_STASH_GUARD=0`.

## 10. Harness↔Provider-Mirror-Parität (ABS-317)

If your change edits ANY `.devin/agents/*.md` or `.devin/skills/*`
file, the `agent_providers/claude_code/` provider mirror is a GENERATED VIEW of
that source and MUST be regenerated in the SAME commit:

```bash
bash scripts/generate-governor.sh --providers   # regenerate the mirror
git add agent_providers/claude_code              # stage it WITH your harness edit
```

Do this BEFORE your handoff — the regenerated mirror travels in the same commit as
the harness edit that caused it, never a follow-up "propagate mirror" commit. Skip
it and the drift is invisible until the Epic-Integration smoke
(`generate-governor.sh --providers --check` / `tests/test-harness-parity.sh`) fails
at 5/6 — on ABS-223 that forced a `git bisect` over 18 commits and a
`Done → Ready for Development` bounce of an already-merged, QA-passed story. A
mechanical pre-commit guard (ABS-317) aborts a commit that stages a harness edit
without its synced mirror and prints this exact fix line; do not work around it.
Kill switch (operator only): `ORCH_MIRROR_GUARD=0`.

## 11. Process-Skill-Gate (invoke before every handoff, ABS-318)

Before you write your handoff, run the universal process skills as an EXPLICIT
checklist step — not a passive afterthought. This is part of your exit
discipline (rule 1), at the decision point, so it actually fires:

- **`stop-slop` — always.** Run it against your written or code deliverable
  (spec, review, doc, PR text, commit, multi-paragraph answer) before you emit
  it. This is the anti-slop gate; skipping it on a due occasion is a gate miss.
- **`verify` — where applicable.** After a code change with a runtime surface,
  drive the changed flow end-to-end (not just re-run tests) before finishing.
- **`simplify` — where applicable.** After substantive code changes, pass over
  the diff for reuse/simplification.

"Where applicable" is scoped by your seat: a review/decision/tracker seat with no
code deliverable runs `stop-slop` only; a seat that edits product source or
`patterns_library/` runs all three. Invoke via the Skill tool — do not re-derive
their content inline. Each role keeps only a one-line pointer back to this rule
(DRY); the trigger lives here once because `_common-rules.md` is prepended to
every seat by the spawn seam (ABS-174), so all roles inherit it.

## 12. Prioritäts-Charter (never raise a ticket's priority, ABS-261)

You NEVER set or raise a ticket's `priority` field (`hotfix`/`high`/`normal`/`low`).
Setting a priority — above all promoting a ticket to `hotfix`, which lets it pass
wartende Feature-Arbeit and overrun the concurrency cap — is a Human/PO board
action only (consistent with ABS-241). A seat that raised its own work to `hotfix`
could starve every peer of slots. Read the priority the tracker gives you; act on
it; do not change it. The orchestrator's priority-aware dispatch (ABS-261) trusts
this: it reads the canonical `priority` field but no seat writes it.
