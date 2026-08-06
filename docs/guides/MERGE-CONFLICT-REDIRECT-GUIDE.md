# Merge Conflict Redirect (PILOT-18)

**Audience:** operators and implementers who work with the reconciliation sweep
and the `Ready for Merge` gate.

---

## Background

On 2026-07-22 (v3-pilot #3) MR !158 was merged while MR !159 sat open at the
`Ready for Merge` gate. The two MRs carried the same Prisma migration number
(`015/015`) and a conflicting `migrate.test.ts`. After !158 landed, !159 could
not merge cleanly. Nothing detected this: the merged-ness sweep only asks "is
the story's commit already in the target branch?" — it never asks "does the open
MR still apply cleanly?" The conflict was invisible until the operator ran
`git merge-tree` by hand, diagnosed the collision, and redirected PILOT-9 to
`Merging` with a written resolution recipe.

PILOT-18 closes that wound: on every sweep cycle the orchestrator checks whether
each `Ready for Merge` story's open MR is still mergeable and, on conflict,
redirects it to `Merging` automatically with the same resolution recipe.

---

## How it works

### 1. Mergeability probe (`story_mergeability`)

For each story in `Ready for Merge` the sweep calls `story_mergeability <ticket>`
before the merged-ness check. It returns exactly one token:

| Token | Meaning |
| --- | --- |
| `CLEAN` | MR applies without conflict (or is already merged). No action. |
| `CONFLICT` | MR cannot merge cleanly — a seat must rebase and resolve. |
| `UNKNOWN` | Cannot be determined (degraded host, missing branch). Fail-open: no action. |

**Forge lane** (`$FORGE_CMD` is set): one `forge pr-state <ticket>` call reads
the adapter's `mergeable=BOOL` field. The adapter seam owns the mapping from the
host-specific field (`GitLab: detailed_merge_status conflict/cannot_be_merged`;
`Bitbucket: mergeable`) onto that single boolean — the orchestrator stays
host-agnostic.

**Pilot lane** (no forge): a hermetic `git merge-tree --write-tree <target-tip>
<branch-sha>` dry-run against the active remote. Exit 0 = `CLEAN`, exit 1 =
`CONFLICT`, anything else = `UNKNOWN`. This is the same probe the operator ran
manually on !159.

The probe never writes and never transitions. `UNKNOWN` never triggers a redirect
(fail-open), so a temporarily unreachable host or an older `git` that lacks
`merge-tree --write-tree` cannot cause false redirects.

### 2. Conflict redirect (`merge_conflict_redirect`)

When `story_mergeability` returns `CONFLICT`:

1. **Flapping guard (AC3):** the redirect fires once per `(MR-head, target-head)`
   pair. The fingerprint (`<mr-sha>:<target-sha>`) is stored in
   `$ORCH_STATE_DIR/merge-conflict-<ticket>`. If neither tip moved since the last
   redirect, the call returns early — no repeated comments, no log spam. A new
   foreign merge (target tip moves) or a rebase (MR head moves) is a fresh
   fingerprint and may redirect again.

2. **Intent line:** `INTENT-MERGE-CONFLICT-REDIRECT` is emitted so the operator
   sees the intervention in the run log without needing to act.

3. **Gate-results comment:** posted on the ticket with the PILOT-9 resolution
   recipe (see below).

4. **Transition:** `Ready for Merge → Merging` under `--expect-from "Ready for
   Merge"`. If the status-table lacks that edge, the gate fails loudly and
   returns without intervening (never silently stalls).

5. **Notification:** sent to the operator channel so the redirect surfaces
   without requiring active polling.

The merged-ness check (`merge_wait_release`) runs unchanged after
`merge_conflict_redirect`. A `MERGED` MR reads as `CLEAN` and the conflict gate
no-ops, so the release path is unaffected (AC4).

---

## Resolution recipe (for the Merging seat)

When you receive a story redirected by `MERGE-CONFLICT-REDIRECT`:

1. **Rebase onto the current target branch** — not the tip it had when the MR
   was opened.
2. **Identify the colliding artefacts.** For migration-number collisions (the
   `015/015` class): draw a fresh migration number with
   `scripts/next-migration-number.sh` **after** the rebase, never before, and
   never guess. Rename the conflicting file(s) accordingly.
3. **Get the test suite green.**
4. **Push with `--force-with-lease`.**

Once the branch is clean and the suite passes, the story returns to the gate via
the normal path.

---

## What this does not do

- **No automatic conflict resolution.** The sweep redirects the story; a seat
  resolves the conflict. Automatic resolution is out of scope for PILOT-18.
- **No webhooks.** The gate polls on each sweep cycle (outbound-only per
  ADR-A-0010, ADR-A-0026 P11). Webhook acceleration remains inside the
  ABS-500 S7 envelope, deferred until the backend is forge-reachable in
  production.
- **No CI/pipeline status.** That is a separate concern.

---

## Configuration

No new environment variables. The gate is always active when a story rests at
`Ready for Merge`. It costs one `forge pr-state` call (forge lane) or one
`git merge-tree` dry-run (pilot lane) per waiting story per sweep cycle.

---

## Conformance tests

`tests/tooling/test-merge-conflict-redirect.sh` — 42 assertions covering AC1 through
AC4:

- A conflicted open MR → transition to `Merging`, recipe reason, intent line
  (AC1).
- A clean or undecidable MR → no action, no log (AC2).
- Same `(MR-head, target-head)` standstill → redirect fires exactly once (AC3).
- Merged-ness check (`merge_wait_release`) stays untouched; a MERGED MR reads
  CLEAN and the conflict gate no-ops (AC4 regression).

The sibling suites (`test-merge-wait.sh`, `test-merge-wait-target.sh`,
`test-ready-for-merge-gate.sh`) pass unchanged — 149 total assertions green.

---

## Related

- `MERGE_GUARD_CHOKEPOINT_GUIDE.md` — the merge-target guard that blocks merges
  onto protected branches (PILOT-11/ABS-513).
- ABS-500 S7 — webhook acceleration for the forge lane (deferred, out of scope
  here).
- ABS-494, ABS-270 — the `merge-wait` machinery this gate hooks into.
- ABS-530 — the depends-release gate (same sweep family).
