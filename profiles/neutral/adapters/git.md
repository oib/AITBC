# Git Repository Adapter — Interface

> _Adapted from the clean-room blueprint. Inline `.agentic/…` names below are design-record concepts; their live homes are in the [crosswalk](../../../blueprint/CROSSWALK.md). Treat this file as the capability contract._

The only surface agents use for repository operations beyond their own working tree. Providers:
GitHub, GitLab, Bitbucket (reference), mock (local branches + PR-as-markdown for dry-runs).
Selected via `config.git.provider`.

## Operations

| Operation | Semantics |
|-----------|-----------|
| `create_branch(name, from)` | Branch per `config.git.branch_naming` (`{type}/{ticket-id}-{slug}`). |
| `diff(ref_a, ref_b)` | Inspect diffs (used by Review Agent packets). |
| `get_commit(ref)` / `reference_commits(ticket_id)` | Commit metadata; ticket-id back-references in messages. |
| `create_pr(branch, target, description)` | Create PR/MR. Description must be rendered from [`.github/pull_request_template.md`](../../../.github/pull_request_template.md). A PR may bundle multiple tickets. |
| `update_pr(id, description)` | Keep gate results/exceptions current. |
| `get_merge_events(callback)` | Merge events drive tickets to `done`. |

## The structural no-merge constraint

**The adapter exposes no merge operation for branches listed in `config.git.protected_branches`.**
This is a hard interface property, not a permission setting: no role manifest, no PO approval,
and no escalation can grant an agent a merge-to-protected capability, because the operation does
not exist in the interface. Provider-side branch protection is configured *in addition* (defense
in depth), but the boilerplate never relies on it alone.

Mock provider: PRs are markdown files under `work/tickets/<TICKET-ID>/pr.md` describing branch,
target, and rendered description; "merge" is the human running `git merge` themselves — which is
exactly the point.

## Degraded rebase-gate (jira/mock profile)

The rebase-gate (epic ABS-392, backing lever 2) requires a story branch to already sit on the
current **epic integration branch** (`epic/<parent>-*`) tip at Story Acceptance, so a late rebase
conflict costs only the Dev step, not the whole gate chain. The v3-native profile
(agentic-backend) computes a `merge_readiness` field from `pr_mirror` and enforces this in the
backend transition guard ([ABS-397]). **This profile has no computed fields**, so the check is
_degraded_ to a git-only test the QAS/PO seat runs by hand — same accept/reject outcome, no
backend. Helper: [`scripts/rebase-gate-check.sh`](../../../scripts/rebase-gate-check.sh) (the load-bearing
primitive is `git merge-base --is-ancestor <epic-tip> <story-branch>`; exit 0 = the epic tip is
already contained = `clean`, exit 1 = `rebase-needed`).

- **Trigger point.** The QAS/PO seat runs the check **at Story-Acceptance exit**, immediately
  before the `Story Acceptance → Merging` transition — _after_ QAS, never instead of it (identical
  placement to the native guard). Fetch the epic branch first; a stale local ref lies.

  ```bash
  scripts/rebase-gate-check.sh gate "epic/<parent>-integration" "<story-branch>" "<transition reason>"
  #   exit 0 -> ACCEPT: proceed with the transition
  #   exit 1 -> REJECT: do NOT transition; rebase first (see below)
  ```

- **Block condition.** `rebase-needed` (the epic tip is not an ancestor of the story branch) blocks
  the move **unless the same move documents a rebase** — the transition reason contains the word
  `rebased` (case-insensitive), the degraded stand-in for the native guard's `/\brebased\b/i`
  event-evidence check. `clean` passes through unchanged. Bad/unknown refs exit `64` (fails closed —
  never a false `clean`).

- **Rebase-record path.** When blocked, the seat rebases the story branch onto the epic tip, re-runs
  `readiness` to confirm `clean`, then performs the `Story Acceptance → Merging` transition with a
  reason that records the rebase (e.g. `rebased onto epic tip <sha>; clean`). That reason IS the
  evidence — it lands verbatim on the transition comment via the task-tracking adapter
  (`transition … --reason-file`), mirroring the payload the native guard stores on the transition
  event.

[ABS-397]: rebase-gate transition guard in the agentic-backend profile (native, computed-field variant).
