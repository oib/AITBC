# Status Source-of-Truth Drift Guard (ABS-404)

**Audience:** implementers adding or renaming a ticket status.

`profiles/neutral/adapters/statuses.yaml` is the canonical status machine. Five
places in the scripts layer embed a copy of the status list, order, or terminal
subset for zero-dependency awk/bash reasons. Before ABS-404, adding a status to
`statuses.yaml` without updating those copies caused silent drift — discovered
only at the release check, not before the merge (the `Canceled` status, ABS-338).

`scripts/status-source-drift-guard.sh` checks all five copies against
`statuses.yaml` in one pass. It is auto-discovered by the `tests/test-*.sh`
loops in `scripts/pre-release-check.sh`, `.github/workflows/tests.yml`, and
`bitbucket-pipelines.yml`, so it fails on the PR — before merge.

---

## The five embedded copies

| Copy | File | What is embedded |
| --- | --- | --- |
| **A** | `scripts/hooks/iteration-guard.sh` | `ranks[]/eranks[]` awk arrays — chain order |
| **B** | `scripts/orchestrator.sh` | `is_known_status()` case list — membership set |
| **C** | `scripts/orchestrator.sh` | three terminal rest-skip functions — terminal subset |
| **D** | `backend/packages/core/src/workflows/statuses.yaml` | byte-identical mirror of the source file |
| **E** | `scripts/fastlane-eligibility.sh` | `IN_FLIGHT="…"` pipe list — active-work membership subset |

**Not copies** (data-driven from `statuses.yaml` at runtime — no drift possible):

- `scripts/jira-tracker.sh` — `CANON_STATUS_LIST` (sed over the file)
- `scripts/orchestrator.sh` — `status_is_terminal()` (awk over the file)
- `scripts/mock-tracker.sh` — status validation (awk over the file)

**Out of scope** (a separate backend-package drift class):
Backend TypeScript files (`packages/core/src/invariants.ts`, `board.ts`,
`apps/server/src/routes/dashboard.ts`, `apps/web/src/util.ts`) embed status
literals. Copy D already pins the backend `statuses.yaml` byte-identical. A
TypeScript-side guard belongs with the backend workspace's own lint/typecheck.

---

## Adding a new status

When you add a status to `profiles/neutral/adapters/statuses.yaml`, update all
five copies before submitting a PR. The guard tells you exactly which copies
drifted; the fix lines name the file to edit.

**Checklist:**

- [ ] `scripts/hooks/iteration-guard.sh` — add the status to `ranks[]` and
  `eranks[]` in document order (Copy A). Exclude `Blocked` and `Needs PO
  Decision` — they are cross-cutting and the guard skips them for A.
- [ ] `scripts/orchestrator.sh` `is_known_status()` — add the status to the
  case list (Copy B).
- [ ] If the status is `terminal: true`: add it to `is_legit_rest_status()`,
  `first_live_claim()`, and `propagate_start_label_to_children()` in
  `scripts/orchestrator.sh` (Copy C).
- [ ] `backend/packages/core/src/workflows/statuses.yaml` — copy the source
  file over the mirror (Copy D):

  ```bash
  cp profiles/neutral/adapters/statuses.yaml \
     backend/packages/core/src/workflows/statuses.yaml
  ```

- [ ] If the new status is an active-work (in-flight) status, add it to
  `IN_FLIGHT` in `scripts/fastlane-eligibility.sh` (Copy E). The reverse
  direction — a new active status *not* added to `IN_FLIGHT` — is not caught
  mechanically (no in-flight attribute exists in `statuses.yaml`); you own that
  decision.

---

## Running the guard locally

```bash
# From the repo root — exits 0 on clean, 1 on drift, 2 on missing source.
bash scripts/status-source-drift-guard.sh
```

A drift failure prints named `DRIFT:` and `fix:` lines per copy:

```
DRIFT: COPY A: iteration-guard.sh ranks[]/eranks[] drifted from statuses.yaml order
  fix: update the ranks[]/eranks[] awk block in scripts/hooks/iteration-guard.sh
    --- statuses.yaml (chain order) ---
        ...Frobnicated...
    --- iteration-guard ranks ---
        ...
status-source-drift-guard: FAIL — statuses.yaml has drifted from an embedded copy (see above).
```

Run the regression test to confirm your fix holds:

```bash
bash tests/test-status-source-drift.sh   # must be 9/9
```

---

## CI wiring

The test file `tests/test-status-source-drift.sh` is auto-discovered by the
`tests/test-*.sh` glob in:

- `scripts/pre-release-check.sh` (line 98)
- `.github/workflows/tests.yml` (line 60)
- `bitbucket-pipelines.yml` (line 138)

No CI configuration edit is needed when you add a new drift test.

---

**Related:** ABS-404 (drift guard implementation), ABS-338 (`Canceled` drift
root cause), `docs/sop/TEST_SUITE_LAYOUT.md` (test file placement rules),
`profiles/neutral/adapters/statuses.yaml` (source of truth).
