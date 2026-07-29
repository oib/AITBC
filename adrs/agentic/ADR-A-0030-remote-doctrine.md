---
id: ADR-A-0030
title: Remote doctrine — the active remote is the sole source of push/merge/probe targets; the release mirror is receive-only
status: proposed
scope: agentic
date: "2026-07-26"
---

# ADR-A-0030: Remote doctrine — the active remote is the sole source of push/merge/probe targets; the release mirror is receive-only

- **Status:** proposed
- **Date:** 2026-07-26
- **Origin:** PILOT-54 (twin ABS-569). The doctrine has been load-bearing since
  2026-07-23 (Operator, PILOT-25) but had no ADR: it lived only in
  `scripts/active-remote-guard.sh`, `scripts/release-mirror-push.sh`, and one knob row of
  `docs/sop/ORCHESTRATOR_SOP.md` attributed to "Operator, 2026-07-23 / PILOT-25". This ADR
  writes the unwritten-but-enforced law down so the code has a decision to point at.
- **Relates to:** ADR-A-0005 (all work reaches main through PRs), ADR-A-0014 (per-epic
  merge gate; main stays human-merge-only), ADR-A-0015 (**provider-config-mirror** — a
  *different* "mirror"; see the disambiguation note there), ADR-A-0021 §(PR-mirror) (the
  backend PR-mirror — a *third* "mirror").
- **Human boundary:** acceptance of this ADR is a human act (ADR-A-0004); the implementer
  and architect leave it `proposed`. Naming/failing-over the active remote is likewise an
  Operator act (see §4).

## Context

This repo has **two reachable git remotes** with distinct, non-interchangeable roles:

- **`gitlab` (gitlab.haemosan.at) — the LIVE remote.** It carries all day-to-day flow:
  story branches, epic integration branches, the runner's pushes, MR-open, merge-detection,
  and the `main` ref the orchestrator resolves work against.
- **`origin` (Bitbucket) — the RELEASE MIRROR.** It receives **only** finished versions —
  `main` + the release tag — at release time, and **nothing else**.

Two reachable remotes without a single declared source-of-truth are a silent divergence
generator. Two concrete incidents already cost Operator hand-repair:

1. **v3-pilot #3:** an RTE seat resolved the push remote to `origin` *by convention*, pushed
   a recovery branch to Bitbucket, and opened PR #236 there. GitLab got nothing; the Operator
   moved the branch + MR (!165) by hand. This is the incident `active-remote-guard.sh` closes.
2. **2026-07-25:** a **hardcoded `origin` fallback in merge-detection** — exactly the bug
   class this doctrine must forbid — fired a **false alarm**, reporting a commit as un-merged
   because it probed the wrong remote.

The term **"mirror" is overloaded three ways** in this repo, which is itself a source of
confusion this ADR must dispel:

- **ADR-A-0015 — the provider-config-mirror:** `agent_providers/claude_code/` etc., a
  generated *view* of `harness/.claude/`. Nothing to do with git remotes.
- **PILOT-25 / this ADR — the release mirror:** the Bitbucket `origin` remote.
- **ADR-A-0021 — the backend PR-mirror:** the backend's mirrored PR/MR state.

This ADR owns the **release-mirror** meaning; ADR-A-0015 is amended in the same change to
name its meaning explicitly (AC2 of PILOT-54).

## Decision

1. **The active remote is the SINGLE source for every push, MR-open, merge-detection and
   probe target.** Any seat or script that pushes, opens an MR, or asks "is X merged / how far
   behind is my branch" resolves the target from the **active-remote pin**
   (`$ORCH_MAIN_REMOTE`, the same knob `orchestrator.sh` reads to resolve the active `main`
   ref, ABS-493) — never from the ambient `origin` convention.

2. **Hardcoded remote names are forbidden in flow code.** No push path, MR path, or
   merge/behind probe may name a remote literally (`origin`, `gitlab`) as its target or as a
   *fallback*. The 2026-07-25 false alarm was precisely a hardcoded `origin` fallback in
   merge-detection; a hardcoded fallback is the same defect as a hardcoded target and is
   equally prohibited. Resolve the remote from the pin, or fail closed — never guess.

3. **The release mirror is RECEIVE-ONLY and never gates.** The mirror remote (Bitbucket
   `origin`, `$ORCH_MIRROR_REMOTE`) receives only `main` + the release tag, only at release
   time, only via `scripts/release-mirror-push.sh` (run in the `/release` flow after the tag
   lands on the LIVE remote). **Mirror availability MUST NEVER gate the release:** any mirror
   failure — remote absent, host unreachable, auth failure — is a WARN and the release still
   completes on the live remote (the script exits 0 on every such failure; only a usage error
   exits non-zero). No seat ever pushes work branches or opens MRs on the mirror.

4. **Failover (active-remote change) is an Operator act.** When the live remote is
   unavailable and a different remote must temporarily become live, the Operator re-points the
   pin (`ORCH_MAIN_REMOTE`) and, if needed, the mirror pin (`ORCH_MIRROR_REMOTE`). Because all
   flow code reads the pin (§1) and never a literal name (§2), a failover is a single
   configuration change, not a code edit. **Unset pin = legacy single-remote repo:** the guard
   is inert and every target is allowed, so a fork with one `origin` is unchanged.

## Consequences

- Push/MR targets and merge/behind probes are deterministic and pin-driven; the
  convention-based Bitbucket push (v3-pilot #3) and the hardcoded-`origin` merge false alarm
  (2026-07-25) are both structurally excluded — §2 forbids the fallback that caused the
  latter.
- The release is decoupled from mirror availability: Bitbucket being down never blocks
  shipping (§3).
- Failover is a config flip, not a code change (§4).
- The three "mirror" meanings are now disambiguated across ADR-A-0015 (provider-config),
  this ADR (release), and ADR-A-0021 (backend PR-mirror).
- **Not closed here (follow-up):** this ADR documents and forbids the hardcoded-`origin`
  merge-detection fallback but does not itself refactor that call site — the remediation of
  the 2026-07-25 defect is tracked separately. `active-remote-guard.sh` today guards
  push/MR-open; extending a mechanical pin-check over merge-detection probes is a candidate
  hardening, not part of this documentation ticket.

## Alternatives considered

- **Leave the doctrine unwritten (status quo).** Rejected: load-bearing law with no ADR is
  exactly what let the 2026-07-25 hardcoded-fallback ship and the v3-pilot #3
  convention-push happen; the code had no decision to point at.
- **One remote only (drop the mirror).** Rejected: the Bitbucket mirror is the deliberate
  release-archive/redundancy path (backend-cutover transition note); removing it loses the
  off-GitLab copy of shipped versions.
- **Mirror gates the release (fail the release if the mirror push fails).** Rejected (§3):
  it would let a Bitbucket outage block shipping, inverting the mirror's receive-only,
  never-gating role.
- **Per-call literal remote names with review discipline.** Rejected (§2): review discipline
  is what already failed twice; the single-pin rule makes the correct target mechanical
  rather than a thing each author must remember.
