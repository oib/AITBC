# Remote Doctrine — GitLab is Live, Bitbucket is the Release Mirror

> **Status:** active doctrine (Operator decision, 2026-07-23). Codified mechanically by
> PILOT-25 (twin ABS-539).

## The doctrine in one line

**GitLab (`gitlab.haemosan.at`) is the permanent LIVE remote. Bitbucket (`origin`) is a
RELEASE MIRROR that receives ONLY finished versions — `main` + the release tag — at release
time. Nothing else is ever pushed to Bitbucket.**

There is exactly **one** legitimate Bitbucket write: the release mirror push in
`scripts/release-mirror-push.sh` (run by the `/release` flow, Phase 4.2b). Every other
push, story branch, and merge request lives on GitLab.

## Why (the trigger)

Two reachable remotes without a pin are a silent divergence source. In v3-pilot #3 (2026-07-23),
after Bitbucket came back online an RTE seat resolved the push remote to `origin` **by
convention**, pushed the PILOT-13 recovery branch to Bitbucket, and opened PR #236 there —
GitLab got nothing. The Operator had to move the branch and MR (`!165`) to GitLab by hand.
Prose alone ("push GitLab, not origin") did not hold; the doctrine is now mechanical.

## The two mechanical controls

### 1. Active-remote pin + guard (every seat)

The active remote is pinned with `ORCH_MAIN_REMOTE=gitlab` (see below). A seat's push / MR-open
**always follows the pin, never the `origin` convention**. Before a push or MR-open a seat runs:

```bash
scripts/active-remote-guard.sh check "<target-remote>"
#   exit 0 = ALLOW  (no pin in force, OR target IS the pinned active remote)
#   exit 1 = REFUSE (a pin is set and target is a DIFFERENT remote, e.g. origin while pin=gitlab)
#   exit 64 = usage error
```

On REFUSE the guard prints a machine-greppable `ACTIVE-REMOTE-GUARD-REFUSE target=… pin=…` line;
retarget the pinned remote (`git push gitlab …`, open the MR on GitLab). When `ORCH_MAIN_REMOTE`
is unset the guard is inert — a single-remote fork with only `origin` is unchanged.

### 2. Release mirror push (release only, WARN-only)

At release time, after `main` + the tag are pushed to the live remote, the finished version is
mirrored to Bitbucket:

```bash
bash scripts/release-mirror-push.sh <version>        # rehearse first with --dry-run
```

**Bitbucket availability never gates the release.** Any failure — mirror remote absent, host
unreachable, auth failure — is a **WARN** and the script still exits 0. This is deliberate: the
release is complete once it is on the live remote; the mirror is best-effort.

## Setup — pin the active remote

Set the pin (launcher / runner environment) and git's own push default so both the orchestrator
and a bare `git push` resolve to GitLab:

```bash
export ORCH_MAIN_REMOTE=gitlab            # runner / launcher env (orchestrator reads this)
git config remote.pushDefault gitlab      # bare `git push` goes to GitLab, not origin
```

The provisioning step sets `remote.pushDefault=gitlab`; the launcher templates export
`ORCH_MAIN_REMOTE=gitlab`. (`ORCH_MAIN_REMOTE` is the same knob `orchestrator.sh` already reads to
resolve the active `main` ref, ABS-493 — one pin, two consumers.)

## Explicitly out of scope

- Back-syncing the ~100 old feature branches to Bitbucket (they stay at their 2026-07-16 state,
  deliberately).
- Bitbucket pipelines / PR flow.
- Deleting the `origin` remote (it stays — it is the mirror target).

## Related

- `scripts/active-remote-guard.sh`, `scripts/release-mirror-push.sh`, `tests/test-remote-doctrine.sh`
- `scripts/merge-target-guard.sh` (PILOT-10/ABS-513) — the sibling guard chokepoint.
- ABS-538 (MR-target guard) — shares the guard-at-the-chokepoint pattern.
