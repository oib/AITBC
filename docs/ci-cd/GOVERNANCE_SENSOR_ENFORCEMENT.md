# Governance Sensor Enforcement — which sensor runs on which path

**Ticket:** PILOT-59 (epic PILOT-58) · **Status:** enforced on the live remote via `.gitlab-ci.yml`

The governance sensors are deterministic checks that keep the rule surface honest
(ADR ids unique, ADR status truthful, the rule ledger complete, the ORCH_* knob
docs in sync, provider skills at parity). This page is the single source of truth
for **where each sensor actually executes**, because "where a check runs" is not
the same as "where the code that gates a merge runs".

## The gap this closes

The active push remote is **GitLab** (`gitlab.haemosan.at`); Bitbucket is only a
release mirror (PILOT-25 doctrine). The sensors historically lived **only** in
GitHub Actions (`.github/workflows/`), which does not run on GitLab. So on the
remote that actually gates merges to `main`, **no sensor ran**. On 2026-07-25 the
`epic/PILOT-28-poll-to-push` branch carried three red ADR guards plus a red knob
guard that would have merged into `main`; only a manual operator run caught them.
The local full-suite gate at the epic integration point does not structurally
close the gap (ABS-557).

`.gitlab-ci.yml` (added by PILOT-59) runs the fast sensors on GitLab on **every
push and every merge request**, so the sensors now execute on the live remote.

## Sensor → path matrix

| Sensor | Backing script | GitHub Actions | GitLab CI (live remote) |
|---|---|---|---|
| ADR id uniqueness | `tests/test-adr-id-uniqueness.sh` | `tests.yml` (full suite) | `.gitlab-ci.yml` job `adr-id-uniqueness` |
| ADR status truthfulness | `tests/test-adr-status.sh` | `tests.yml` (full suite) | `.gitlab-ci.yml` job `adr-status` |
| Rule ledger completeness | `scripts/rule-ledger-check.sh` | `pr-validation.yml` | `.gitlab-ci.yml` job `rule-ledger` |
| ORCH_* knob doc drift | `scripts/orch-knob-doc-drift.sh` | `tests.yml` (full suite) | `.gitlab-ci.yml` job `knob-doc-drift` |
| Provider skills parity | `.github/scripts/check-skills-parity.sh` | `pr-validation.yml` | `.gitlab-ci.yml` job `skills-parity` |

Each sensor is its own GitLab job, so a single failing sensor (for example a
duplicate ADR number turning **only** `adr-id-uniqueness` red) is independently
visible and independently blocking.

## Why GitLab CI and not a pre-push hook

Both are valid live-remote paths (a pre-push hook gates before the push reaches
GitLab). GitLab CI was chosen because a **hard pre-push blocker cannot be
deployed onto a tree that already has a red sensor** — doing so would block every
push, including the push of the fix. At the time PILOT-59 landed, `rule-ledger`
and `skills-parity` were already red on `main` (the exact drift this ticket
predicts reaches the live remote uncaught). GitLab CI reports that drift without
bricking pushes: the push succeeds, the pipeline goes red, and the merge is
blocked. Pre-existing red sensors are therefore surfaced, not hidden — which is
the point — and they are fixed under their own tickets.

## The one human-only step

A red pipeline blocks a merge **only** when *Settings → Merge requests →
"Pipelines must succeed"* is enabled on the protected target branch(es). That is
a project-settings change and thus human-only (ADR-A-0004); `.gitlab-ci.yml`
cannot enable it for itself. Until it is enabled, the pipeline still runs and
reports on every push — the redness is visible — but a determined merge can
override it.

## Falsification (AC3)

A branch that introduces a duplicate ADR number turns the `adr-id-uniqueness`
job red, so with "Pipelines must succeed" enabled the branch cannot merge. The
sensor's bite is pinned two ways:

- `tests/test-adr-id-uniqueness.sh` self-checks synthetic duplicate fixtures.
- `tests/test-governance-remote-path.sh` asserts `.gitlab-ci.yml` actually wires
  every sensor above, and drives the real ADR-id sensor against a planted
  duplicate to prove the wired check exits non-zero.
