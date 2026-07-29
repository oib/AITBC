# Sandbox Guard SOP (PILOT-46 / ABS-546, PILOT-62)

**Audience:** implementers adding backend- or tracker-touching tests.

---

## What the guard does

`tests/sandbox-guard.sh` unsets four vars that carry live credentials when
sourced at the top of a test entrypoint:

- `BACKEND_URL`
- `BACKEND_TOKEN`
- `TRACKER_CMD`
- `ORCH_INSTANCE_ID`

These vars are inherited from the operator's shell. Without the guard a test
that references the backend writes to PROD — the incident that motivated this
mechanism flooded the Mission Control board twice (~1750 and ~1000 junk rows).

**Escape hatch.** Set `ORCH_TEST_ALLOW_BACKEND=1` before sourcing to skip the
unsets. Use this only for live-conformance tests that intentionally hit the
real backend; never in normal CI.

---

## What the CI check enforces

`scripts/sandbox-guard-check.sh` fails CI (exit 1) when any entrypoint in
`tests/` that *touches* the backend or a tracker adapter does not source the
guard. "Touches" is derived mechanically from the **code** of the file: any
entrypoint whose non-comment lines match `BACKEND_URL|BACKEND_TOKEN|TRACKER_CMD|
ORCH_INSTANCE_ID|backend-tracker|mock-tracker|backend-shipper|shipper`
is required to source `sandbox-guard.sh`. `run-all.sh` is always required
regardless of content. Full-comment lines (first non-whitespace char `#`) are
excluded: a test that merely *names* `backend-shipper.sh` in a header comment
does not touch the backend at runtime, and flagging it would be a false RED
(PILOT-62).

```bash
bash scripts/sandbox-guard-check.sh    # exit 0 = all entrypoints guarded
```

---

## Adding a new backend-touching test

1. Create `tests/test-<ticket>-<slug>.sh`.
2. Near the top, after `set -...`, add:
   ```bash
   # shellcheck source=tests/sandbox-guard.sh
   . "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"
   ```
3. Run `bash scripts/sandbox-guard-check.sh` locally — it must report the new
   file in its OK count.

---

## Fixture discipline for tests that test the check itself

`test-sandbox-guard.sh` tests the CI check via a synthetic fixture directory.
Two rules keep those fixtures from producing false-green results.

**Rule 1 — use `${TMPDIR}`, not `work/`.**

`work/scratch` is gitignored. In a fresh clone it does not exist. `mktemp -d`
targeting a gitignored parent either fails (returning an empty string) or
produces a path that `SANDBOX_GUARD_TESTS_DIR=""` coerces to blank, causing
the check to fall back to the real `tests/` dir. The negative assertions then
measure a repo that legitimately passes — a vacuum-green result.

```bash
# WRONG — gitignored parent, fails in a clean checkout
FIX="$(mktemp -d "$REPO_ROOT/work/scratch/sgc-XXXXXX")"

# RIGHT — always available
FIX="$(mktemp -d "${TMPDIR:-/tmp}/sgc-fixture-XXXXXX")"
```

**Rule 2 — prove the check detects a gap in the REAL repo.**

A fixture of synthetic files proves the mechanism works on hand-built input.
It does not prove the real-repo scan is non-vacuous. After the synthetic
negative test passes, add a counter-proof case:

```bash
REAL="$(mktemp -d "${TMPDIR:-/tmp}/sgc-real-XXXXXX")"
trap 'rm -rf "$FIX" "$REAL"' EXIT
cp "$SCRIPT_DIR"/*.sh "$REAL"/

# baseline: unmutated copy must pass (redness is attributable to the mutation)
out="$(SANDBOX_GUARD_TESTS_DIR="$REAL" bash "$CHECK" 2>&1)"; rc=$?
assert_eq "$rc" "0" "unmutated copy of the real tests dir passes"

# remove the guard-source line from a REAL backend-touching entrypoint
victim=""
for f in "$REAL"/test-*.sh; do
  b="$(basename "$f")"
  if grep -qE "$TOUCH_RE" "$f" && grep -qE 'sandbox-guard\.sh' "$f"; then victim="$b"; break; fi
done
grep -v 'sandbox-guard\.sh' "$REAL/$victim" > "$REAL/$victim.tmp" && mv "$REAL/$victim.tmp" "$REAL/$victim"
out="$(SANDBOX_GUARD_TESTS_DIR="$REAL" bash "$CHECK" 2>&1)"; rc=$?
assert_eq "$rc" "1" "removing the guard line from $victim turns the check red"
assert_contains "$out" "$victim" "check names the file"
```

This pattern (PILOT-62) is already in `tests/test-sandbox-guard.sh`. Maintain
it when adding entrypoints or modifying the check.

---

## Root cause of the vacuum-green incident (PILOT-62)

Prior to PILOT-62, the fixture in `test-sandbox-guard.sh` was built under
`$REPO_ROOT/work/scratch`. That path is in `.gitignore`, so it is absent in a
fresh clone or worktree. There `mktemp` failed silently, leaving `FIX=""`; a
blank `SANDBOX_GUARD_TESTS_DIR` made the check scan the real `tests/` dir
instead of the fixture. The three negative assertions then ran against a repo
that already passed, so they always passed — including when a real entrypoint
was missing the guard line.

The working negative test then immediately found a genuine gap:
`tests/test-run-status-collector.sh` was touching the tracker adapter without
sourcing the guard. That file now sources it, and the entrypoint count rose
from 35 to 36.

**Takeaway:** any `mktemp` inside a test that writes fixture files must target
`${TMPDIR:-/tmp}`, not a path under `work/` (gitignored) or the repo root
(pollutes the working tree).

---

**Related:** `tests/sandbox-guard.sh`, `scripts/sandbox-guard-check.sh`,
`tests/test-sandbox-guard.sh`, `.github/workflows/pr-validation.yml` (CI
wiring), ABS-546 (original story), PILOT-62 (vacuum-green fix).
