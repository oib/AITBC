# QA Validation — PILOT-25
**Remote Doctrine: GitLab live, Bitbucket = Release Mirror**
Validated by: qas | Date: 2026-07-24 | Commit: `5b66f7f6`

## Verdict: APPROVED

All three acceptance criteria pass. No blocking findings.

---

## AC1 — release-mirror-push.sh (WARN-only, never gates release)

**Requirement**: after a GitLab tag, `origin main+tag` is pushed; an unreachable origin runs
with WARN and exits 0.

**Validation**: ran `bash tests/test-remote-doctrine.sh` against commit `5b66f7f6`.

Sections C and D cover AC1 — 11 tests, all pass:

| Test | Result |
|------|--------|
| no tag → exit 64 (usage) | PASS |
| non-semver tag → exit 64 (usage) | PASS |
| dry-run → exit 0 | PASS |
| dry-run → prints DRY-RUN OK | PASS |
| dry-run pushed nothing (mirror has no 'main' ref) | PASS |
| real push to reachable mirror → exit 0 | PASS |
| mirror now has refs/heads/main | PASS |
| mirror now has the release tag v9.9.9 | PASS |
| unreachable mirror → exit 0 (release NOT gated) | PASS |
| unreachable mirror → prints WARN | PASS |
| mirror remote absent → exit 0 (release NOT gated) | PASS |

Script logic confirmed: the push failure path falls through to `warn … exit 0`; only missing
or non-semver tag triggers `die … exit 64`. Bitbucket availability cannot gate the release.

**AC1: PASS**

---

## AC2 — active-remote-guard.sh (conformance: pin=gitlab refuses origin)

**Requirement**: with `ORCH_MAIN_REMOTE` set, a seat push/MR-open targeting `origin` is
refused (exit 1 + machine-greppable intent line); the pinned remote is allowed; no pin =
guard inert.

**Validation**: sections A and B of the test suite — 9 tests, all pass:

| Test | Result |
|------|--------|
| pin=gitlab, target origin → REFUSE (exit 1) | PASS |
| target origin → prints ACTIVE-REMOTE-GUARD-REFUSE intent line | PASS |
| pin=gitlab, target gitlab → ALLOW (exit 0) | PASS |
| pin=gitlab, target origin/main → REFUSE (normalised, exit 1) | PASS |
| pin=gitlab, target gitlab/PILOT-25-auto → ALLOW (normalised, exit 0) | PASS |
| no pin (ORCH_MAIN_REMOTE unset), target origin → ALLOW (exit 0) | PASS |
| no pin (ORCH_MAIN_REMOTE empty), target origin → ALLOW (exit 0) | PASS |
| missing target → exit 64 (usage, fails closed) | PASS |
| unknown subcommand → exit 64 | PASS |

`remote/branch` normalisation confirmed: `origin/main` strips to `origin`, `gitlab/PILOT-25-auto`
strips to `gitlab`. Guard is inert when `ORCH_MAIN_REMOTE` is unset or empty (single-remote
forks unchanged).

**AC2: PASS**

---

## AC3 — Documentation names the doctrine and the one legitimate Bitbucket write

**Requirement**: docs name the remote doctrine and identify the only legitimate Bitbucket write
(release mirror).

Files in commit `5b66f7f6` covering AC3:

| File | Coverage |
|------|----------|
| `docs/guides/REMOTE_DOCTRINE_GUIDE.md` (new, 80 lines) | States the doctrine in one line; calls out "There is exactly **one** legitimate Bitbucket write"; documents both mechanical controls; setup section for the pin |
| `CONTRIBUTING.md` (§ Push Changes) | Callout block names the release-mirror role of Bitbucket; links to the guide; replaces hardcoded `origin` with `${ORCH_MAIN_REMOTE:-origin}` |
| `harness/claude/commands/release.md` (Phase 4.2b) | New phase titled "Mirror the release to Bitbucket (release mirror — WARN-only)" with the explicit note "This is the ONLY legitimate Bitbucket write" |
| `harness/claude/agents/rte.md` + `agent_providers/claude_code/prompts/rte.md` | Adds pin rule to the RTE seat; both files updated in parity |
| `docs/sop/ORCHESTRATOR_SOP.md` | `ORCH_MAIN_REMOTE` entry expanded with doctrine pointer |

**AC3: PASS**

---

## Quality gates

| Check | Command | Result |
|-------|---------|--------|
| Test suite | `bash tests/test-remote-doctrine.sh` | **20/20 PASS** |
| Shellcheck (warning severity) | `shellcheck -S warning scripts/release-mirror-push.sh scripts/active-remote-guard.sh tests/test-remote-doctrine.sh` | **exit 0** (clean) |
| Harness parity | `bash scripts/generate-governor.sh --providers --check` | **exit 0** (rte.md source + mirror match at `268cab3f`) |

---

## Scope / hygiene

- Commit `5b66f7f6` changes exactly 9 files (+426/-6): 2 new scripts, 1 new test, 1 new doc,
  4 updated docs/agent files, harness mirror regenerated in the same commit.
- No product code touched (backend, frontend, DB, RLS — all out of scope per ticket).
- Pattern reuse: `ORCH_MAIN_REMOTE` pin and merge-target-guard shape; no new env var beyond
  `ORCH_MIRROR_REMOTE` (optional override, documented).
- No `design` flag on ticket — exit target is `Story Acceptance`.

---

## Summary

All 20 test assertions pass. Shellcheck and harness-parity gates are clean. AC1 (WARN-only
mirror), AC2 (guard refuses wrong remote, inert without pin), and AC3 (doctrine + single
legitimate write documented in four locations) are fully met.

**Verdict: APPROVED for Story Acceptance.**
