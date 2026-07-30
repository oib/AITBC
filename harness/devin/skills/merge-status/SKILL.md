---
name: merge-status
description: "One-command PR / CI / merge-drift status checks for the RTE seat \u2014\
  \ answer \"is commit X on main?\", \"is PR N open or merged?\", \"is my branch behind\
  \ the target?\" in a SINGLE tool call whose EXIT CODE is the answer, instead of\
  \ the fetch\u2192log\u2192pr-view\u2192read\u2192interpret ritual that burns the\
  \ turn ceiling. Use whenever you need to know the state of a PR, a merge, or CI\
  \ without changing anything; also use to decide whether to keep waiting or hand\
  \ off."
triggers:
- user
- model
allowed-tools:
- exec
- read
---

# Merge status (RTE polling, without the turn-fraß)

All paths are relative to the repo root. Host CLI is `bb` (Bitbucket) on this repo.

The RTE seat has a 60-turn ceiling and the classic way it gets eaten is
**status polling**: `git fetch`, then `git log`, then `bb pr view`, then read the
output, then interpret it — four turns to answer one yes/no question, repeated
every time you wonder "did it land yet?". Transcript mining (ABS-221) found
25× `git log`, 7× `git fetch`, 4× `git ls-remote`, 4× `bb pr view`, 3× `bb pr
list` across a handful of RTE sessions.

This skill replaces that ritual with **one command per question**, where the
**exit code is the answer**. Branch on `$?`; do not re-read and re-parse the
printed line (it is for the transcript, not for your logic).

## The one-command checks

The wrapper `merge-status.sh` is committed next to this file. Run it, then
branch on its exit code.

```bash
SKILL=harness/devin/skills/merge-status/merge-status.sh   # source copy: harness/devin/skills/merge-status/

# "Is commit X on main?" — did the merge actually land?
"$SKILL" on-target <commit> [target]     # exit 0 = on origin/<target>; 1 = not yet

# "Is PR N open or merged?"
"$SKILL" pr-state <id>                    # exit 0 = MERGED; 3 = OPEN; 4 = declined/other

# "Is CI green on PR N?"
"$SKILL" pr-ci <id>                       # 0 green; 1 FAILED; 2 no checks; 3 still pending

# "Is my branch behind the target (rebase drift)?"
"$SKILL" drift <branch> [target]          # exit 0 = up to date; 1 = behind (rebase)
```

Composed use — branch on the code, never on the text:

```bash
if "$SKILL" on-target "$MERGE_SHA" main; then
  echo "landed — proceed to Docs handoff"
else
  echo "not landed — do NOT busy-wait; see 'When NOT to poll' below"
fi
```

## Exit-code contract (branch on these)

| Command                     | 0            | 1              | 2            | 3            | 4                    |
|-----------------------------|--------------|----------------|--------------|--------------|----------------------|
| `on-target <commit> [tgt]`  | on target    | not on target  | —            | —            | —                    |
| `pr-state <id>`             | MERGED       | —              | —            | OPEN         | declined/superseded  |
| `pr-ci <id>`                | all green    | a check FAILED | no checks    | still pending| —                    |
| `drift <branch> [tgt]`      | up to date   | behind (rebase)| —            | —            | —                    |

Usage / not-found / auth errors exit `64`. Defaults: `target=main`, host CLI
`bb`, remote `origin` (override via `GIT_HOST_CLI`, `ORIGIN`).

## Raw `bb` recipes (what the wrapper runs)

If you need a field the wrapper does not expose, use `bb --json --jq` directly —
it filters in-process, so you get the one value instead of a screen to read:

```bash
bb pr view <id>   --json --jq '.state'                                   # OPEN|MERGED|DECLINED
bb pr view <id>   --json --jq '.merge_commit.hash'                       # the landed sha
bb pr checks <id> --json --jq '.summary | "\(.successful) \(.failed) \(.pending)"'
bb pr list        --json --jq '.pullRequests[] | .id'                    # open PR ids (list defaults to OPEN)
git merge-base --is-ancestor <sha> origin/main                          # exit 0 = landed
git rev-list --count <branch>..origin/main                              # commits behind target
```

Prefer `git merge-base --is-ancestor` over `git log | grep` — it is a pure
exit-code test, no output to read.

## When NOT to poll (hand off instead)

**`Ready for Merge` / final merge to `main` is human-owned** (ADR-A-0004/0005;
orchestrator.sh lesson, the `Ready for Epic Acceptance` NOTIFY seam). Once a PR
is CI-green and review-complete, your job is **done** — you hand off to HITL and
**stop**. Do not sit in a fetch/`pr-state` loop waiting for a human to click
merge: that is exactly the turn-burn this skill exists to kill.

- CI still `pending` (`pr-ci` exit 3): note it in the handoff and stop — do not
  busy-wait for the build. The next seat / a resumed spawn re-checks in one call.
- PR still `OPEN` awaiting human merge (`pr-state` exit 3): hand off, do not poll.
- Only poll when *you* have an imminent action gated on the result (e.g. the
  next story in an epic merge sequence needs the previous one landed) — and even
  then, one `on-target` call, not a loop.

## Gotchas (all hit for real against PR #153)

- **`--jq` string scalars come back quoted** (`"MERGED"`). The wrapper strips the
  quotes; if you call `bb ... --jq` yourself, strip them (`| tr -d '"'`) before
  comparing.
- **`bb pr checks` returns exit 0 even with zero checks** — the summary is
  `{successful:0, failed:0, pending:0}`. "No checks configured" (`pr-ci` exit 2)
  is NOT the same as "green"; don't treat it as a pass without confirming CI is
  expected to run.
- **`on-target` needs a fetched target.** The wrapper does `git fetch origin
  <target>` first; a raw `git merge-base --is-ancestor` against a stale
  `origin/main` will lie. Fetch, then test.
- **A merged PR's merge_commit is behind `main`** as `main` moves on — `drift`
  counting 8 behind for #153's merge sha is expected, not a problem.
