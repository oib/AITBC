---
id: ADR-A-0013
title: Self-hosting — a pinned stable release governs development; promotion is release
status: accepted
scope: agentic
date: "2026-07-05"
accepted_by: Raphael Sahann (POPM)
accepted_date: "2026-07-05"
---

## Context

The boilerplate is the governance system for agentic development, yet it is developed from its
own source. Without a structural split the rules governing the agents (`CLAUDE.md`, hooks, agent
definitions, skills) are the same live bytes an agent is being asked to edit. Two failure modes
follow: meta-level confusion (an agent treats a harness file as a rule to obey rather than content
to change) and live-fire hazard (editing a hook or settings file mutates the running session
mid-edit). ABS-63 introduced per-file write boundaries and a human co-op step to manage the
second hazard on the live config path — a heavyweight, per-file ceremony.

Epic ABS-91 replaces that footing with a self-hosting model: develop vNext under an installed
copy of the **last release**, so the boilerplate becomes its own first consuming project. This ADR
codifies that model and its release semantics. It builds on prior phases already landed in
2.17.0: ABS-92 (Phase 1 operating mode + seams), ABS-96 (`harness/.claude` product namespace),
and ABS-94 (`generated(pin)` live tree + drift guard).

## Decision

We adopt the following, together, as the self-hosting model:

**1. Compiler-bootstrap rule.** Never build stage N+1 with stage N+1. Development of vNext is
governed by a pinned checkout of the last release; everything in the dev repo is inert work
product carrying no authority.

**2. Two-checkout operating mode (ABS-92 seams).** A pinned **stable** checkout (`~/boilerplate-
stable`) supplies the governing rules and scripts; the **dev** repo is only the work target
(`ORCH_TARGET_REPO`, `ORCH_HARNESS_HOME`; interactive via `scripts/dev-session.sh`). Isolation is
**tiered**: interactive sessions are fully governed by stable (rules load there, the dev repo is
attached with `--add-dir`); headless spawns are **agent-definitions-only** isolated — they read
role defs from stable but keep cwd = the dev repo so they can edit the code — until the drift
guard pins the live tree, which is the mechanism that makes the boundary structural rather than
behavioral.

**3. Structural split of the shipped harness.** `harness/.claude` is the inert **SOURCE** (ABS-96):
agents edit it as ordinary work product with **no per-file ceremony**. The live `.claude/` is
**`generated(pin)`** (ABS-94) where the pin is `.governor-tag`: never hand-edited, materialized by
`scripts/generate-governor.sh`, and defended by the drift guard (`tests/test-harness-parity.sh`
runs `generate-governor.sh --check` in CI). A direct edit to the live tree fails mechanically.

**4. Promotion = release (human-gated, whole-version).** The live governor rolls forward only at a
release, as one whole version — it fits the ADR-A-0008 release boundary and leaves the ADR-A-0004
human-only merge/cost boundaries untouched. Cutting a release, in order, on a single commit:
regenerate `.claude/` from the version being released, stamp the provenance banner with that
version, bump `.governor-tag` to it, commit, then tag on that commit. The result is the invariant
that makes a released tag safe to consume: **`.claude@vN == generate(vN)`** — a consumer syncing
the legacy `.claude` domain at tag `vN` (default `UPSTREAM_PATH=.claude`) gets exactly the
generated form of that release. `scripts/promote-release.sh <tag> [--dry-run]` makes this
mechanical (H5); pushing the tag and updating `~/boilerplate-stable` remain human steps.

**5. Escape hatch.** A governor bug is fixed by a **patch release** of stable and a re-checkout of
the new tag — never an in-place edit of the stable checkout, which stays a clean pinned release at
all times. To shake out `harness/.claude` work before promotion, govern a **throwaway** checkout
under a **release-candidate tag** (the ABS-94 RC-dogfooding procedure): RC tag → throwaway
checkout with its own pin → generate → govern with it → discard. The released governor and the
main repo's drift guard are never touched by an RC dogfood.

## Consequences

The dev-repo harness files carry no authority; "rule or deliverable?" has a mechanical answer
(the provenance banner + the compiler-bootstrap rule). Harness-source edits are ordinary edits, so
the common case of harness work loses all ceremony. The live tree cannot drift silently: the guard
rejects hand-edits. The governor deliberately lags one release; that lag is the safety property,
not a defect. Post-v3, each release is developed under the previous release's orchestrator — every
release is a full dogfood.

**Supersession of ABS-63.** This ADR replaces MOST of the ABS-63 per-file write-boundary ceremony.
Because the shipped harness now has its editable SOURCE at `harness/.claude/**` (an ordinary,
non-`.claude` path outside the headless `.claude/` write guard), a ticket whose deliverables are
harness content targets `harness/.claude/…` directly and needs **no staging + human-install
co-op**. The ABS-63 ceremony survives ONLY for (a) legacy / non-self-hosted setups that still edit
a live `.claude/` as their source, and (b) any direct edit to the live `.claude/` runtime tree —
which the drift guard now **rejects mechanically** (CI fails), so the sanctioned path there is a
promotion, not a hand-edit. The historical procedure is retained in the ORCHESTRATOR_SOP "Known
Limitations" section for those two cases; it is no longer the default.

## Related Decisions

- **ADR-A-0004** (Humans own irreversibility) — untouched; promotion is a release, and its
  human-only merge/cost boundaries continue to bound every path to production.
- **ADR-A-0005** (All work reaches main through PRs) — promotion lands through the normal PR/merge
  gate; the release commit + tag are prepared by the script and pushed by a human.
- **ADR-A-0008** (Boilerplate ownership + version-tracked upgrades) — promotion-as-release is the
  whole-version boundary this ADR relies on; the governor rolls forward one whole version at a time.
- **ADR-A-0002 / ADR-A-0003** (fresh subagent execution / context minimization) — the agent-defs-
  only spawn isolation resolves role definitions from the stable checkout.

## References

- Epic ABS-91 (self-hosting: stable governs dev); stories ABS-92 (Phase 1), ABS-96 (namespace,
  `docs/agent-outputs/ABS-96-layout-decision.md`), ABS-94 (generated governor), ABS-95 (this ADR +
  promotion script).
- `specs/DRAFT-self-hosting-stable-governs-dev-spec.md` — design spec (H1–H5 acceptance cases).
- `scripts/generate-governor.sh`, `scripts/promote-release.sh`, `tests/test-harness-parity.sh`.
- `docs/sop/ORCHESTRATOR_SOP.md` — "Stable-Governs-Dev Mode", "RC dogfooding", "Known Limitations".
- ABS-63 — the per-file write-boundary ceremony this ADR supersedes for self-hosted setups.

## Amendment note

**Status.** Accepted 2026-07-05 by Raphael Sahann (POPM) — sign-off given via the epic PR #36
review/merge and the explicit acceptance statement recorded in the ABS-91 closeout; the status
flip was directed by the POPM. Future amendments follow the normal ADR amendment process.
