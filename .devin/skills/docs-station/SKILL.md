---
name: docs-station
description: "Tech-Writer Docs-station recipes \u2014 verify the story's implementation\
  \ PR is merged (worktree-less merge-base gate), inspect and edit docs on the story\
  \ branch without a checkout, validate markdown (markdownlint with awk line-length\
  \ fallback), and run the Docs->Done exit-precondition checklist. Use at the `Docs`\
  \ seat before writing docs or transitioning a story to `Done`."
triggers:
- user
- model
allowed-tools:
- edit
- exec
- glob
- grep
- read
- write
---

# Docs station (Tech-Writer)

Copy-paste recipes for the `Docs` seat — the last stage before `Done`
(`Merging -> Docs -> Done`). Everything here is worktree-less: you inspect
other branches with `git show`/`git ls-tree`, never `git checkout`. All paths
are relative to the repo root. Every code block below was executed for real
against this repo (ABS-220 AC2, run-boilerplate / PR #153 standard).

> **This seat has no `Skill` tool** (the tech-writer `tools:` frontmatter is a
> hard allowlist — `Read, Write, Edit, Grep, Glob, Bash`, no `Skill`; ABS-123).
> A headless seat therefore cannot *invoke* this skill — `Read` this file and
> apply the recipes verbatim, exactly as it applies `stop-slop`.

## Prerequisites

None beyond a dev machine: `git`, `awk`. `markdownlint` is optional — this repo
ships no `markdownlint` binary and no `package.json`, so recipe 3 falls back to
`npx markdownlint-cli2` when reachable and an awk line-length gate otherwise.
Do not burn turns on `which markdownlint` / `yarn lint:md` — they are absent by
design; recipe 3 already handles it.

## Recipe 1 — Merge-status gate (Docs->Done precondition, ABS-211)

A story may leave `Docs` for `Done` **only** when its implementation PR is
**merged onto the target/epic branch**. This is the seat-side mirror of the
runner's `done_pr_gate` (fail-closed on anything not cleanly merged). Verify it
worktree-less with `merge-base --is-ancestor` — no forge CLI needed:

```bash
# 1. From the Merging handoff: the story branch head SHA (or origin/<story-branch>)
#    and the target/epic branch NAME it was merged onto.
ORIGIN="${ORIGIN:-origin}"   # git remote — e.g. origin, or `gitlab` on the fallback remote
STORY_SHA="dcfbdeb"          # e.g. origin/ABS-XXX-auto head, from the Merging handoff
TARGET="main"                # the target/epic branch NAME (e.g. main, or the epic branch)
                             # — a branch name, NEVER local HEAD.

# 2. Fetch the remote target ref, then test containment against the REMOTE
#    tracking branch ($ORIGIN/$TARGET) — never local HEAD. A stale/unfetched
#    local checkout never contains the remote merge, so testing HEAD traps a
#    merged-on-remote story in a NOMOVE loop (ABS-452). This mirrors the proven
#    merge-status.sh:49-50 pattern.
git fetch -q "$ORIGIN" "$TARGET"

# 3. Merged == the story commit is fully contained in the remote target branch.
if git merge-base --is-ancestor "$STORY_SHA" "$ORIGIN/$TARGET"; then
  echo "MERGED — Docs->Done precondition satisfied"
else
  echo "NOT MERGED — stay in Docs, post gate-results naming the open PR"
fi
```

**Conformance example (ABS-452 stale-HEAD regression).** ABS-452's impl commit
`e518a6b` was human-merged onto `gitlab/main` (MR !109, tip `7d57500`), but the
runner's local checkout was never fetched, so local `HEAD` did not contain it.
With the old `TARGET="HEAD"` default the check ran
`git merge-base --is-ancestor e518a6b HEAD` → exit `1` → "NOT MERGED" forever,
looping `Docs` into the respawn-limit dump (twice, ~4 wasted seats). The recipe
above instead runs, on the `gitlab` fallback remote:

```bash
ORIGIN=gitlab STORY_SHA=e518a6b TARGET=main
git fetch -q gitlab main                                   # pulls tip 7d57500
git merge-base --is-ancestor e518a6b gitlab/main && echo MERGED   # -> exit 0, MERGED
```

Because it fetches the remote target and tests `gitlab/main` (not local `HEAD`),
the merged-on-remote story is detected as MERGED and Docs -> Done proceeds.

`--is-ancestor` exits `0` (merged / contained) or `1` (not merged). It is exact
for merge-commit and rebase merges (this repo merges with a merge commit:
`Merged in <branch> (pull request #NNN)`). For a **squash** merge the branch
head is not an ancestor — then trust the Merging handoff's `Result: merged`
line (and the forge state where a `$FORGE_CMD` is configured) instead of the
SHA test. When in doubt, fail closed: leave the story in `Docs`.

## Recipe 2 — Inspect docs on the story branch (worktree-less)

You are already on your own worktree/branch, so edit the story's docs directly
with `Edit`/`Write` and commit them. To *read* what exists on another branch
(the merged story branch, the target branch) without a checkout:

```bash
# List the docs present on a branch — no checkout.
git ls-tree -r --name-only HEAD -- docs/ | head

# Read one file as it stands on that branch.
git show HEAD:.devin/skills/README.md | head -3
```

Swap `HEAD` for `origin/<story-branch>` or `origin/<target-branch>` to inspect
any ref. This replaces the repeated `git show <branch>:docs/...` probing with
one deliberate call.

## Recipe 3 — Validate the docs (markdownlint fallback + line-length)

```bash
TARGET=".devin/skills/README.md"   # the doc you wrote/updated

# Prefer a real linter; fall back gracefully (no markdownlint binary in this repo).
if command -v markdownlint >/dev/null 2>&1; then
  markdownlint "$TARGET"
elif command -v npx >/dev/null 2>&1 && npx --no-install markdownlint-cli2 --version >/dev/null 2>&1; then
  npx --no-install markdownlint-cli2 "$TARGET"
else
  echo "markdownlint unavailable — awk structural fallback only"
fi

# Line-length gate: flag lines > 120 chars, skip fenced code blocks. Always available.
awk 'BEGIN{f=0} /^```/{f=!f} { if(!f && length($0)>120) printf "%s:%d: %d chars\n",FILENAME,NR,length($0) }' "$TARGET"
```

`npx --no-install markdownlint-cli2` runs the linter only when it is already
cached; it never triggers a network install. If neither path is available the
awk gate still catches the most common CI failure (over-long lines).

## Recipe 4 — Exit-precondition checklist (Docs -> Done)

Before transitioning, confirm ALL of these (ABS-211; a `Done` with an open PR
is a false signal for the epic JOIN and the runner bounces it back to
`Merging`):

- [ ] Implementation PR **merged** onto the target/epic branch — recipe 1 exits
      `0`, or the Merging handoff records `Result: merged`.
- [ ] Docs written/updated for the shipped change (feature-guide / api-reference
      / migration-guide per `patterns_library/documentation/`).
- [ ] Validation clean — recipe 3 reports no blocking markdown / line-length
      errors.
- [ ] `handoff` comment posted: files written/updated (absolute paths) +
      validation result.
- [ ] `gate-results` comment posted with the merge evidence (recipe 1 outcome).

Only when every box is checked, transition with your handed adapter
(`$TRACKER_CMD`; do NOT invent one):

```bash
mkdir -p work/scratch
printf '%s\n' "Docs: documentation written + validation green, implementation PR merged — story Done" \
  > work/scratch/<story-id>-reason.md
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <story-id> "Done" --actor tech-writer \
  --reason-file work/scratch/<story-id>-reason.md
```

If the PR is **not** merged: do NOT transition. Post a `gate-results` comment
naming the still-open PR and leave the story in `Docs` so the merge completes
first. You never merge (ADR-A-0004/0005).

## Success metric (ABS-220 AC4)

- **Baseline (today):** 81x `ls`-probing + repeated `git show <branch>:docs/...`
  + `which markdownlint` across 12 tech-writer sessions; 2 turn-cap deaths at
  the 25-turn default (ABS-173); the NOMOVE loop of ABS-211.
- **Target:** median tool-calls per tech-writer seat in the next live run
  **< 50 %** of the baseline value.
- **How to measure (before/after):** the ABS-120 cost report aggregates spawns
  per seat from the structured run log —

  ```bash
  scripts/orchestrator-report.sh "$ORCH_STATE_DIR/run.log"
  ```

  Count the tech-writer seat's tool invocations from the same run log's
  transcript lines and compare the run-over-run median against the baseline.

## Gotchas (all hit for real)

- **No `markdownlint`, no `package.json`, no `yarn lint:md`** in this repo —
  recipe 3's fallback is the supported path; stop probing for the binary.
- **Squash merges break `--is-ancestor`** — the branch head is not contained in
  the target. Fall back to the Merging handoff `Result: merged` line.
- **`git fetch` before recipe 1** — a stale `origin/<target>` makes a merged PR
  look unmerged and traps the story in a NOMOVE loop (ABS-211).
- **You have no `Skill` tool** — `Read` this file and apply it; do not try to
  invoke it via a `Skill` call (it will be permission-denied under the seam's
  `--permission-mode dontAsk`; ABS-123).
