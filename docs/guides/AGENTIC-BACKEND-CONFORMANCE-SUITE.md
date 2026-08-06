# Phase-3 Knowledge Conformance Suite

ABS-384 (ABS-231 S7) wires Spec §10 conformance cases into the backend test suite.
Any regression in ADR import, policy resolution, the `policies` op, packet injection,
or the human-only guards is a release blocker.

---

## What the suite covers

Seven §10 cases, each pinned to a named test:

| §10 Case | Test | File | What it validates |
| --- | --- | --- | --- |
| Case 1 | Test 17 | `test-backend-tracker.sh` | ADR import → 200 + `imported:1`; no-op re-import idempotent; unknown status → 422 |
| Case 2 | Test 18 | `test-backend-tracker.sh` | `supersedes:` link triggers auto-Superseded transition on the older ADR |
| Case 3 | Test 19 | `test-backend-tracker.sh` | Policy resolution matrix: org-only, audience-scoped, project-override, empty; byte-stable `policy_rev` on repeated calls; golden-fixture exact byte-match; cache-invalidation when policy set changes |
| Case 4 | Test 16 | `test-backend-tracker.sh` | `policies` adapter op parity (S4/ABS-381 tests registered as §10 release-blocker) |
| Case 5 | Test 22 + ABS-382 block | `test-backend-tracker.sh` + `test-orchestrator.sh` | `ORCH_POLICY_INJECT=off` → no `=== POLICY` block; two distinct policy payloads → two distinct `policy_rev` values in the packet header → cache invalidated; `run.log` records `POLICY-INJECT` audit line |
| Case 6 | Test 20 | `test-backend-tracker.sh` | Human-only rejections: orchestrator token → ADR→Accepted → 403; orchestrator token → policy write → 403; ADR `→ eligible` fires DB-level CHECK. Hard-FAIL on token-mint failure. |
| Case 7 | Test 21 | `test-backend-tracker.sh` | Export → CONF2 import round-trip including ADRs; ADR key and type preserved |

Total: 187 assertions across Tests 1–22 (Tests 16–22 are the §10 block).

---

## Running the suite

```bash
# From repo root. Requires Docker with compose plugin.
bash tests/tooling/test-backend-tracker.sh
```

The script provisions a throwaway compose stack (backend + ephemeral Postgres), seeds a
`CONF` project, runs all 22 tests, and tears the stack down on exit. When Docker is
unavailable it exits 0 with a `SKIP` message — this mirrors the DB-gated backend unit
tests and is not a failure.

The orchestrator-side §10/Case 5 tests run as part of the orchestrator suite:

```bash
bash tests/tooling/test-orchestrator.sh
```

Run the lint gate separately:

```bash
bash tests/tooling/test-tracker-adapter-lint.sh
```

The lint gate (21 assertions) verifies that all seven `§10/Case N` markers are present
in the conformance suite. Remove any marker and the lint fails.

---

## Golden fixtures

Two files record expected byte-for-byte output from the policy resolver:

| Fixture | Path | Validates |
| --- | --- | --- |
| Empty-render | `tests/fixtures/phase3-golden-empty-render.txt` | `(no applicable policy)` — the canonical text when no policy applies to a role |
| Policy matrix | `tests/fixtures/phase3-golden-policy-matrix.txt` | Rendered Markdown for the org+audience constellation (Org Standards + BE Code Style) |

**If you change the policy renderer's output format**, update the fixtures:

```bash
# Run Test 19 to capture the new output, then overwrite.
# The test prints the actual rendered text before the assertion fails.
bash tests/tooling/test-backend-tracker.sh 2>&1 | grep -A 20 "Test 19"

# Overwrite with the verified new output.
printf '%s\n' "<new output>" > tests/fixtures/phase3-golden-empty-render.txt
printf '%s\n' "<new output>" > tests/fixtures/phase3-golden-policy-matrix.txt
```

The lint gate checks that both fixture files exist and contain structural markers
(`(no applicable policy)` and `##` section headers respectively). A wrong fixture
content fails the lint — proving the check bites.

---

## Human-only guard verification (Test 20 / §10/Case 6)

Test 20 proves the ADR-A-0004 guards hold end-to-end against a live backend.

| Guard path | Token used | Expected status | On mint failure |
| --- | --- | --- | --- |
| ADR → Accepted transition | orchestrator (Bearer) | `403` | Hard-FAIL |
| `POST /api/v1/.../policies` (write) | orchestrator (Bearer) | `403` | Hard-FAIL |
| Tracker update `labels=[orchestrator-ready]` on ADR | N/A (direct DB) | non-zero exit | N/A — DB CHECK fires unconditionally |

Positive controls: the same operations with a human admin token return `200`/`201`.

Tests 20a and 20b produce a `FAIL` line (not a silent `PASS`) when the orchestrator
token cannot be minted. A security-flagged release gate must not go green because its
setup failed.

---

## CI registration

`bitbucket-pipelines.yml` runs the `tests/tooling/test-*.sh` glob, which auto-includes:

- `tests/tooling/test-backend-tracker.sh`
- `tests/tooling/test-orchestrator.sh`
- `tests/tooling/test-tracker-adapter-lint.sh`

The lint gate requires all seven `§10/Case N` markers to be present. Removing any
marker from the conformance suite fails CI.

---

## Related

- Phase-3 knowledge layer (ADR lifecycle, policy resolution, packet injection):
  `docs/guides/AGENTIC-BACKEND-KNOWLEDGE.md`
- Packet injection SOP (`ORCH_POLICY_INJECT`, `policy_rev` audit): `docs/sop/ORCHESTRATOR_SOP.md`
- ADR import operator procedure: `docs/sop/ADR-IMPORT-RUNBOOK.md`
- HTTP routes and adapter subcommands: `docs/guides/AGENTIC-BACKEND-API.md`
- Conformance suite source: `tests/tooling/test-backend-tracker.sh` (Tests 16–22; §10 block at
  the `§10 Conformance Cases 1–7` comment)
- Orchestrator §10/Case 5 block: `tests/tooling/test-orchestrator.sh` (`ABS-382 / §10/Case 5` section)
- Lint gate source: `tests/tooling/test-tracker-adapter-lint.sh` (Phase-3 section at
  `Phase-3 knowledge conformance registration`)
- Golden fixtures: `tests/fixtures/phase3-golden-empty-render.txt`,
  `tests/fixtures/phase3-golden-policy-matrix.txt`
- Phase-3 spec: `specs/ABS-231-phase3-spec-draft.md` (attached to epic ABS-231)
