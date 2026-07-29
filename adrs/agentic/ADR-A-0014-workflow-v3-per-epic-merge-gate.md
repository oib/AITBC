---
id: ADR-A-0014
title: Workflow v3 — per-epic integration branch; gated auto-merge onto it; main stays human-merge-only
status: accepted
scope: agentic
date: "2026-07-06"
accepted_by: "Raphael Sahann (POPM)"
accepted_date: "2026-07-06"
---

## Context

Workflow v3 (epic ABS-69) closes the last open seat of the full-agent-team orchestrator: the RTE
`Merging` seat. Its design (spec §3.5, `#EXPORT_CRITICAL`) introduces a **per-epic integration
branch**: story PRs land on the epic's own branch, not on `main`, so a human tests and merges an
entire epic's integrated work in **one** PR instead of clicking merge once per story. Agents never
merge to `main` — no environment knob changes that; the epic-branch-to-`main` merge is a normal
human-clicked PR like every other path to `main`.

This decision therefore **operates entirely within** the human-only boundaries already fixed by
ADR-A-0004 (merges to `main` are human) and ADR-A-0005 (all work reaches `main` through PRs) — it
moves no boundary and weakens no gate. What it introduces is new: a branch layer *below* `main` and,
gated on this ADR's acceptance, story-level **auto-merge onto that epic branch**. That is the real
trust decision this record exists to gate — agents integrating each other's accepted stories on the
epic branch **without a per-story human review** — and it is a contained one: a human still
inspects, tests on staging, and merges every epic PR before any of it reaches `main`, so the blast
radius of the trust shift is bounded to a disposable per-epic branch.

The activation is deliberately staged. No auto-merge code path may run until (1) a human **accepts
this ADR** (per ADR-A-0001, agents cannot accept ADRs) **and** (2) the `ORCH_AUTOMERGE` knob is on
(default off) — see part 5. Until both hold, story PRs onto the epic branch are merged by a human,
exactly as ADR-A-0005 requires today; only the target branch (epic branch, not `main`) is new. The
v3 rollout order (spec §6, open question 5) lands every other seat first and auto-merge **last**,
precisely because auto-merge is the one seat gated on this human sign-off.

## Decision

We adopt a per-epic integration-branch policy for Workflow v3, **within** the ADR-A-0004/A-0005
human-only `main` boundaries (which this ADR does not touch). All five parts hold together.

**1. Per-epic integration branch.** Every epic gets its own long-lived integration branch:
**`epic/AITBC-XX-{short-description}`** (e.g. `epic/ABS-69-workflow-v3-full-agent-team`)
— namespaced with an `epic/` prefix so it reads as a branch class at a glance, otherwise following
the same `AITBC-{number}-{description}` convention as story branches
(`.claude/skills/safe-workflow/SKILL.md`, `CONTRIBUTING.md`). **The RTE `Merging` seat owns
epic-branch creation**: as **step 0 of merging the epic's first accepted story**, if
`origin/epic/AITBC-XX-{description}` does not yet exist RTE creates it off
`origin/main` and pushes it, then proceeds with the story merge; every subsequent story of that
epic finds the branch already present. (Creation is lazy and single-owner precisely so no separate
seat or race can leave a story merge targeting a non-existent branch.) **Story branches PR into the
epic branch — never into `main`.** `main` is untouched by any of an epic's stories until the epic
itself is merged (part 3).

**2. Agent auto-merge scope is the epic branch only — never `main`.** The RTE `Merging` seat may
**auto-merge story PRs into the epic branch** on green CI, processed **sequentially per epic in
acceptance order**: for each story it rebases onto the latest **epic branch** tip, re-runs CI, and
merges only on green — then repeats for the next story against the new epic-branch tip
(rebase-first, unchanged from CONTRIBUTING.md). Branch protection on the **epic branch** leans
entirely on CI once auto-merge is active: with no human at the story merge, the CI gate is the sole
mechanical guard there. **Branch protection on `main` is unchanged** — a human merge is required on
every PR that targets `main`, exactly as ADR-A-0004/0005 already require, because no story PR, and
no auto-merge path, ever targets `main`. The human's per-story merge attention does not disappear;
it relocates to the epic boundary (see part 3).

**3. The only path to `main` is a human-merged epic PR; rejection is forward-fix.** When the epic
reaches `Ready for Epic Acceptance` (after staging deploy + smoke, part 4), a PR from the epic
branch to `main` is what the human tests and merges — one human decision, one merge click, for the
whole epic. This is a normal ADR-A-0005 mandatory PR like any other; ADR-A-0004's "merges to main"
human gate is not touched, relocated, or automated in any way.

**Epic-branch sync-rebase (the single sanctioned rewrite).** The epic PR, like every PR in this
repo, must be up-to-date with `main` and rebase-and-mergeable (CONTRIBUTING.md: rebase-first,
"Rebase and merge" only). To keep the epic branch current without merge commits — which would break
both linear history and rebase-and-merge of the epic PR — RTE **rebases the epic branch onto
`origin/main` and pushes `--force-with-lease`**. This is the **sole permitted rewrite of
the epic branch** (see part 4's discipline). It runs **at minimum immediately before RTE releases
the epic to `Ready for Epic Acceptance`** (i.e. before the human opens the epic PR), and **may** run
periodically while the epic rests in `Stories In Flight` to keep drift small. It is safe by
construction: in-flight story branches are unaffected because part 2 already rebases every story onto
the **current epic-branch tip** at merge time, so wherever the sync-rebase moves the tip, the next
story merge rebases onto it fresh. A forward-merge of `main` into the epic branch is deliberately
**not** used (it would create merge commits and defeat the linear, ticket-tagged history that part
4's bisect depends on).

**Sync-rebase conflict → abort, never a silent agent resolution.** A sync-rebase can conflict when
`origin/main` has advanced over the same files an epic touched (main drift, or a second
epic's merged work). An agent must **not** hand-resolve such a conflict — that would push unreviewed
integration into what the human is about to test. Instead RTE runs `git rebase --abort` (leaving the
epic branch **exactly as it was**, no partial rewrite) and transitions the epic to `Blocked`, naming
the conflicting paths in the blocker comment. The existing v3 `Blocked` flow takes over: TDM triages
(classify, resolve/reroute, or escalate a genuinely human-only call), and resolution resumes the
epic to its recorded pre-blocked status (`Epic Integration`) to retry the sync-rebase. This is the
one sanctioned failure branch of the sync-rebase; it changes no `main` boundary and rewrites
nothing.

**Epic rejection = forward-fix, never a revert.** When the human **rejects** the epic PR at
`Ready for Epic Acceptance`, the feedback routes to `Grooming` (spec §3.5): BSA turns it into
new/changed stories that run the story pipeline and merge onto the **still-living epic branch**
(part 2), and the epic re-proposes its PR to `main` once integrated again. There is **no revert** —
`main` was never touched, so there is nothing on `main` to revert, and the epic branch is
forward-fixed, not reset.

**Epic-less stories are explicitly out of scope of this ADR**: follow-up stories created outside an
epic (spec §3.4; default `Backlog`) have no epic branch to target and keep today's flow unchanged —
a per-story PR merged to `main` by a human (ADR-A-0005 / ADR-A-0004, unaffected by this ADR).

**4. Epic-Integration bisect runs on the epic branch, before a human ever sees it.** This decision
adds **exactly one** new edge to the ticket status machine: `Done -> Ready for Development`. It is
the **sole sanctioned exit from `Done`**, used **only** by the RTE Epic-Integration bisect (spec
§3.5, §1.1 `Epic Integration`) to reopen a merged-but-faulty story that a mechanical bisect over the
epic branch has isolated — entirely before the epic branch is proposed to a human as a `main`-bound
PR. This **deliberately breaks the previous "Done is terminal" invariant** (today's status machine
rejects `Done -> *`, e.g. `Done -> Needs PO Decision rejected (Done is terminal)`). The break is
**in scope for this decision** (architecture-review finding 4) and is narrow by construction:
`Done` gains this one outgoing edge and no other; the reopen is an integration-driven bounce, not a
general reopen capability.

**Bisect mechanic (over ticket-tagged linear history).** Stories land on the epic branch via
rebase-first merges (part 2), so the epic branch is a **linear commit range** and every commit
carries its story's `[AITBC-XXX]` tag (commit convention, CONTRIBUTING.md /
`.claude/skills/safe-workflow/SKILL.md`). On an epic-level smoke failure, RTE runs a mechanical
`git bisect` over that linear range against the smoke check, isolates the **culprit commit**, and
maps it to its story via the ticket tag in the commit message. **The endpoints are defined
explicitly**, because the smoke (and therefore any bisect) runs *after* the sync-rebase has already
moved the branch: `git bisect start <epic-tip> <merge-base(epic, origin/main)>` — **bad**
= the current epic-branch tip, **good** = the epic branch's merge-base with `origin/main`
**after the sync-rebase** (i.e. the post-rebase fork point, which carries none of the epic's story
commits), and the **epic-level smoke hook is the bisect predicate**. The sync-rebase re-writes every
story commit's SHA but preserves the linear order and the ticket tags, so the range stays well-formed
and the culprit→story mapping is unaffected. **Edge cases route to `Needs PO Decision`** (never a
guess): the culprit commit lacks a `[AITBC-XXX]` tag, or the tag maps ambiguously to more
than one in-scope story.

**Bad-story mechanic**: the epic branch is **never reset or rebuilt** to fix an isolated story. RTE
reopens exactly that story (`Done -> Ready for Development`); the story's fresh implementation pass
produces a new/updated PR that merges back onto the epic branch (part 2, same sequential rebase +
CI), landing on top of the epic branch's current tip — which still carries every other story that
integrated cleanly. This is the simplest sound mechanic available: it needs no branch reset and no
history rewrite of the epic branch, and it is the same "forward-fix, never revert" discipline the
workflow already uses everywhere else, applied one level down — here to the epic branch instead of
to `main`. **Because `main` never contains any of an epic's unaccepted work, "no agent ever reverts
main" is now trivially true** (there is nothing of the epic's on `main` yet to revert). The operative
epic-branch discipline is: **no agent resets or force-rewrites the epic branch, except the single
sanctioned sync-rebase onto `origin/main` in part 3** — that one rebase is the only rewrite
permitted; all story integration and every bad-story fix is forward-only (new commits, never a
reset).

**5. Activation gate + instant policy rollback.** The auto-merge-onto-epic-branch path is gated
behind **BOTH** conditions, together:

   1. **this ADR is `Accepted`** by a human (per ADR-A-0004 / ADR-A-0001 — agents cannot accept
      ADRs), **AND**
   2. the environment knob **`ORCH_AUTOMERGE=1`** (default **`0` / off**).

   With either condition unmet, the RTE `Merging` seat prepares the story PR **against the epic
   branch** and **stops at the human per-story merge** exactly as today — the ADR-A-0005
   mandatory-PR flow is the default, only the target branch changes (epic branch, not `main`).
   Flipping **`ORCH_AUTOMERGE=0`** restores human per-story merges onto the epic branch
   **instantly, with zero code change** and no redeploy: it is a policy switch, not a migration.
   This makes the trust shift reversible in one environment edit and lets a consuming project run
   Workflow v3's orchestration while keeping human per-story merges (onto the epic branch)
   indefinitely. **In no configuration of this knob does any agent gain the ability to merge to
   `main`** — the knob only ever changes who clicks merge on the epic branch.

## Consequences

### Positive

- Humans move from N story-merge clicks per epic to **one epic-branch-to-`main` merge** decision —
  the merge attention relocates to the boundary where integration risk against `main` is actually
  assessable, and where a human can run the fully-integrated epic on staging before merging it.
- The trust shift is **reversible in one env edit** (`ORCH_AUTOMERGE=0`); adoption is opt-in and
  per-project, and the default posture (human merges every story PR, now onto the epic branch) is
  unchanged from today's per-story flow in spirit.
- ADR-A-0004's and ADR-A-0005's human-only `main` boundaries are **fully respected**: `main` gains
  no agent-merged commits under any configuration of this ADR; the only commits agents ever place
  under a CI-only gate live on a disposable per-epic branch that a human reviews, tests, and merges
  before it ever touches `main`.
- Epic-branch integration is validated as a **sequence** (rebase + CI after each merge) rather than
  as independent story snapshots, catching combination breaks earlier and containing them to the
  epic branch.

### Negative / trade-offs

- Branch protection on the **epic branch** now **depends entirely on CI quality** once
  `ORCH_AUTOMERGE=1`. A weak or flaky CI suite becomes a direct epic-branch risk with no human
  backstop at the story merge — the CI gate must be trusted before `ORCH_AUTOMERGE=1` is set. This
  risk is contained to the epic branch; it does not propagate to `main` because the epic PR is
  still human-reviewed and human-merged.
- `Done` is **no longer terminal**. Downstream consumers of the "Done is terminal" invariant
  (reporting, metrics, any automation asserting `Done -> *` is rejected) must accept the single
  `Done -> Ready for Development` edge. Mitigated by keeping it the *only* new outgoing edge.
- Sequential per-epic merging **serializes** an epic's story merges onto its epic branch; a stuck
  rebase/CI on one story stalls the remainder of that epic's integration (bounded by the story's
  rework counter → the `Needs PO Decision` human gate).
- One additional long-lived branch per epic (the integration branch) must be created, kept current
  with `main` via the sanctioned sync-rebase (part 3), and eventually retired (deleted after the
  epic PR merges to `main`, mirroring today's story-branch cleanup) — a small additional piece of
  git-branch bookkeeping compared to stories PRing straight to `main`. The sync-rebase is the one
  place the epic branch is force-pushed; it is safe because in-flight story branches re-rebase onto
  the epic tip at merge time regardless (part 2).

## Risk analysis (sim scenario S5)

Sim scenario **S5 — Combination break** (spec §5) exercises the core hazard: two individually-green
stories whose *combination* breaks the epic branch at rebase or at integration smoke. Two
mitigations, layered, contain it — entirely upstream of `main`:

1. **Sequential merge + rebase + re-run CI (onto the epic branch)** catches the conflict at the
   **second story's rebase** (the second merge rebases onto an epic-branch tip that already
   contains the first, so the break surfaces as a CI failure and the story bounces — it never
   reaches the epic branch, let alone `main`).
2. If the break only manifests at epic level, **RTE Epic-Integration runs a mechanical `git bisect`**
   over the epic branch's **linear, ticket-tagged commit range**, isolates the culprit commit, maps
   it to its story via the `[AITBC-XXX]` tag, and **reopens that story via the new
   `Done -> Ready for Development` edge** (bounce + forward-fix onto the epic branch, part 4). If the
   culprit commit has no ticket tag or the tag maps ambiguously → `Needs PO Decision` (human).

**Trust-shift rationale.** The trust decision this ADR gates is story-level integration on the epic
branch without a per-story human review: a human merge click per story is replaced by a CI gate —
but that CI gate governs only the **epic branch**, a disposable integration surface that a human
still inspects, tests on staging, and merges by hand before any of it reaches `main`. The shift is
real but **contained**, and it is **not** a shift in who merges to `main` — that gate is exactly as
human-only after this ADR as before it (ADR-A-0004/A-0005, both untouched). The activation gate
(part 5) is the deliberate brake on the epic-branch shift — it cannot occur silently (requires an
Accepted ADR *and* an explicit env opt-in) and is reversible in one env edit. This is why the
auto-merge seat is sequenced **last** in the v3 rollout (spec §6 Q5) and why this record exists as a
standalone human sign-off gate.

## Amendment 2026-07-16 (ABS-336) — Autonomous integration-conflict resolution

**Context.** Part 3 makes the RTE `Epic Integration` seat sync-rebase the epic branch onto `main`
before releasing the epic. When that rebase hits a **conflict**, RTE aborts (branch untouched) and
blocks the epic for triage — the spec-conformant behaviour (spec §3.5). Live evidence (**ABS-314**,
2026-07-16) showed this is where autonomy ends today: the TDM blocker-triage seat has no route for
this class, so the epic rests in `Blocked` awaiting a human. This amendment adds the missing
autonomous resolution path. **It moves no ADR-A-0004/A-0005 boundary** — `main` stays human-merge-
only, and RTE **stays abort-only** (it never resolves a conflict, never rewrites the branch).

**Normative resolution path.** When an epic is `Blocked` **from** `Epic Integration` with a
`sync-rebase conflict` transition reason, the runner's Blocked triage recognises the class
**`integration-conflict`** (Blocker taxonomy of ADR-A-0018) and, instead of ending at the tdm/human
triage:

1. **Forward-fix spawn.** The runner spawns one implementer seat. Its role is taken from the
   `role:` field of the ticket named by the RTE gate comment (`Failing commit: <sha> … [<id>]`);
   absent/unreadable, it defaults to `be-developer`. The spawn carries a packet note with the
   resolution doctrine:
   - **MERGE, do not rebase.** The seat **merges `origin/main` into the epic branch** (a merge
     commit is expected) and **must not** rebase, cherry-pick, reset, or otherwise rewrite history.
     This is a **deliberate, bounded exception** to part 3's rebase-only discipline: resolving a
     conflict autonomously requires a stable base, and the resulting merge commit lives **only on the
     disposable epic branch**, which a human still tests on staging and merges to `main` by hand
     (part 3). No rewrite of a pushed epic branch under an in-flight sibling occurs, so the ABS-314
     force-push hazard part 3 guards against is avoided by construction.
   - **Feature-Union doctrine.** Each conflict hunk keeps **both** sides' features; a sibling story's
     work is never dropped to clear a conflict.
   - **Green + evidence.** The full test suite must pass, and the seat's handoff must carry a
     `commits:` line naming the merge commit(s) (verified per ADR-A-0024/ABS-255).
2. **Re-review, then repeat integration.** On the forward-fix seat's clean handoff the runner routes
   the epic to **`Architecture Review`** — not straight back to `Epic Integration`. The architect
   re-reviews the freshly merged epic branch; releasing it flows back through `Stories In Flight` to
   `Epic Integration`, where **RTE repeats the integration** (now against a merged, conflict-free
   branch). RTE's role is unchanged and still abort-only.

**Kill-switch.** `ORCH_INTEGRATION_CONFLICT_ROUTE=0` restores the pre-ABS-336 behaviour (tdm-only
triage), matching the ABS-111 env-knob convention. Every other Blocked class (including a non-
`sync-rebase` block from `Epic Integration`, or a `sync-rebase`-worded block from any other origin)
keeps the legacy tdm triage untouched.

## Amendment 2026-07-26 (PILOT-53 / ABS-562) — the actual mechanical gate on a pipeline-less remote

**Context.** Part 2 states that once `ORCH_AUTOMERGE=1`, "with no human at the story merge, the CI
gate is the sole mechanical guard there." That sentence assumes a CI pipeline **exists** on the
remote. On the live GitLab remote it does **not** — the project ships no `.gitlab-ci.yml`, so no
server-side pipeline runs on a push or MR. Every entry in the RTE merge log (`work/merge-log.md`)
records this verbatim ("No pipeline configured on GitLab"). Part 2's "sole mechanical guard" is
therefore, on that remote, **not** a server-enforced CI run. This amendment names what the mechanical
guard actually is there, so the ADR no longer implies a protection the remote does not provide. **It
moves no ADR-A-0004/A-0005 boundary** — `main` stays human-merge-only in every configuration.

**The actual mechanical gate (pipeline-less remote).** When no server pipeline exists, the RTE
`Merging` seat substitutes a **seat-run** gate before merging a story PR onto the epic branch, and
records the outcome as merge evidence. It has three parts:

1. **Seat-run test suite.** RTE runs the repo's own suite locally (the `tests/test-*.sh` set
   auto-discovered by `scripts/pre-release-check.sh`) as the merge predicate, in place of the absent
   server pipeline.
2. **Merge-log evidence.** The result — the suite outcome plus the explicit "No pipeline configured on
   GitLab" note — is appended to `work/merge-log.md`, one line per merge, as the durable record that
   the gate ran (and was substituted, not skipped).
3. **Base-integrity check.** RTE verifies the merge base before merging (the story is rebased onto the
   current epic-branch tip and the base is the expected commit), so a story cannot land against a
   stale or unexpected base.

**Known gap — do not read this as "green CI."** The seat-run suite is a substitute, not an equal, of a
server-enforced pipeline: it runs with the seat's own authority and environment, and per **ABS-557**
the seat-run suite does not currently complete cleanly on the epic branch. Until either a
`.gitlab-ci.yml` is delivered (the companion execution-path story) **or** the seat-run suite is made
reliably green, the epic-branch guard on the live remote is **weaker** than part 2's text implies. The
real backstop before anything reaches `main` therefore remains the **human epic-PR review + staging
test** (part 3) — always required, never automated.

**Acceptance.** This amendment corrects a factual claim in an accepted ADR; like the ADR itself it is
human-accepted (ADR-A-0004 / ADR-A-0001 — agents cannot accept ADRs). It is prepared by the
implementer for the normal human PR-review acceptance gate; no agent accepts it.

## Related Decisions

- **ADR-A-0025** (Per-epic merge token) — **refines this ADR** (does not supersede it). Part 2's
  "sequentially per epic, in acceptance order" was never mechanically enforced (the runner locks
  per *ticket*, not per *epic*), which allowed a sibling-merge/rebase-bounce livelock; A-0025 adds
  the runner-enforced per-epic merge token and **narrows part 3's optional periodic sync-rebase to
  `Epic Integration` only**, so the epic tip cannot move under a story that is fixing its rebase.
  A-0025 is `proposed`; until a human accepts it, part 3's text here governs unchanged.
- **ADR-A-0004** (Humans own irreversibility — fixed approval boundaries) — **unchanged and
  respected, not amended**: this ADR moves no ADR-A-0004 boundary. The "merges to main" boundary is
  untouched — `main` remains human-merge-only in every configuration of this ADR — and so are all
  the others (architecture changes, breaking changes, production deployments, accepted ADRs, feature
  initiation, credential provisioning, cost approval). What this ADR adds sits *below* that
  boundary: a new intermediate surface (the per-epic integration branch) where story-level
  integration may, when explicitly opted in, proceed under a CI gate instead of a per-story human
  merge — a surface ADR-A-0004 never governed, because ADR-A-0004 governs `main`. No agent ever
  reverts `main`, and — by construction, since `main` carries no epic's unaccepted work — no agent
  resets or force-rewrites an epic branch either. (Earlier drafts of this ADR carried
  `amends: ADR-A-0004`; that was dropped once the corrected decision made clear no A-0004 boundary
  moves.)
- **ADR-A-0005** (All work reaches main through PRs) — **unchanged and respected**: every story PR
  and the epic PR both carry full description/evidence; the change is *which branch* a story PR
  targets (the epic branch, not `main`) and *who/when* clicks merge on that intermediate branch —
  whether a PR eventually reaches `main` and who merges it there is untouched (a human, via PR).
- **ADR-A-0009** (Cost approval gate) — unchanged: auto-merge introduces no new cost source.
- **ADR-A-0002** (Fresh task-scoped subagents) — the RTE `Merging` and `Epic Integration` seats run
  as fresh subagents like every other seat.
- **ADR-A-0001** (Three-level ADR hierarchy) — placement (agentic scope) and the human-only
  acceptance of this ADR (agents cannot accept ADRs).

## References

- Epic **ABS-69** (Workflow v3 full agent team); stories **ABS-78**, **ABS-88** (this ADR),
  **ABS-89**, **ABS-90**.
- `specs/ABS-69-workflow-v3-full-agent-team-spec.md` — **§3.5 Merge and integration policy**
  (`#EXPORT_CRITICAL`), §1.1 epic pipeline (`Epic Integration`, `Ready for Epic Acceptance`), §1.2
  story pipeline (`Merging`), §5 sim scenario **S5**, §6 open question 5 (rollout order).
- Architecture-review findings (round-2/round-3) — finding 4 (the `Done -> Ready for Development`
  edge breaks "Done is terminal").
- `specs/ABS-36-orchestrator-spec.md` — current status machine and `Ready for Development` role
  selection (the reopen target of the new edge).
- `.claude/skills/safe-workflow/SKILL.md`, `CONTRIBUTING.md` — existing branch naming convention
  that the `epic/AITBC-XX-{description}` integration-branch name extends.

## Sign-off

**Status: Accepted.** This ADR is a human sign-off gate on story-level auto-merge onto epic
branches. Acceptance lifts the ADR half of the part-5 activation gate; the `ORCH_AUTOMERGE` default
remains `0` (off) regardless of acceptance, so no auto-merge code path activates until that knob is
also explicitly set. In no configuration does this ADR grant any agent the ability to merge to
`main`.

Acceptance is a human decision (ADR-A-0004 / ADR-A-0001 — agents cannot accept ADRs). Recorded
below (mirroring the ADR-A-0013 acceptance record).

- **Decision:** ☑ Accepted ☐ Rejected
- **Name / role:** Raphael Sahann, POPM
- **Date:** 2026-07-06
- **Notes / conditions:** Accepted after Opus adversarial review (findings F1–F4 closed in
  c3e628d). ORCH_AUTOMERGE remains 0 by default; findings closure verified before any activation.
