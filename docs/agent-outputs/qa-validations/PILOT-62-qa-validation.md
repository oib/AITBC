# QA Validation Report — PILOT-62

**Ticket**: PILOT-62 — Sandbox-Guard-CI-Check besteht seinen eigenen Negativtest nicht  
**Branch**: PILOT-62-auto  
**HEAD at validation**: e8944d15416c07beb5dad82427b6a1efdb04875c  
**Date**: 2026-07-26  
**Actor**: qas  
**Verdict**: APPROVED

---

## Test Results

All tests run in a detached worktree at e8944d15, clean env (`env -i HOME PATH TMPDIR`).

| Suite | Result |
|-------|--------|
| `tests/test-sandbox-guard.sh` | **12/12 passed, 0 failed** |
| `tests/test-docs-identifier-check.sh` | **7/7 passed, 0 failed** |
| `scripts/sandbox-guard-check.sh` (real repo) | **OK — all 36 backend/tracker entrypoints source the guard** |
| `shellcheck -S warning` (all three scripts) | **rc 0** |

### test-sandbox-guard.sh breakdown

```
== guard strips inherited backend/tracker env ==
  PASS all four vars unset by default
== escape hatch keeps env ==
  PASS ORCH_TEST_ALLOW_BACKEND=1 leaves BACKEND_URL intact
== locally-assigned value after sourcing survives ==
  PASS post-source local assignment survives
== CI check passes on the real repo ==
  PASS sandbox-guard-check exits 0 on repo
  PASS reports OK
== CI check FAILS a fixture that omits the guard ==
  PASS check fails when entrypoints omit the guard
  PASS flags run-all.sh
  PASS flags backend-touching test
== CI check passes once the fixture entrypoints source the guard ==
  PASS check passes once the guard is sourced
== counter-proof: removing the guard line from a REAL entrypoint turns the check red ==
  PASS unmutated copy of the real tests dir passes
  PASS removing the guard line from real entrypoint test-agent-def-lint.sh turns the check red
  PASS check names the real entrypoint test-agent-def-lint.sh

sandbox-guard: 12/12 passed, 0 failed
```

---

## Acceptance Criteria

**AC1** — test-sandbox-guard.sh green, three negative cases name the missing file: ✅  
Tests `check fails when entrypoints omit the guard`, `flags run-all.sh`, `flags backend-touching test` all PASS. The check exits 1 and names both synthetic missing files.

**AC2** — Root cause documented: ✅  
`docs/sop/SANDBOX_GUARD_SOP.md` (Rule 1 / Rule 2 sections) and inline test comments explain the cause. The original fixture used `mktemp -d "$REPO_ROOT/work/scratch/…"`. `work/scratch` is gitignored — absent in a clean checkout, `mktemp` fails, `SANDBOX_GUARD_TESTS_DIR=""` falls back to the real `tests/` dir, and the negative assertions measured a repo that legitimately passes. Rule-ledger entry R-1106 ("Root cause of the vacuum-green incident (PILOT-62)") pins this in the ledger.

**AC3** — Real-repo counter-proof baked into the suite: ✅  
Test case `removing the guard line from real entrypoint test-agent-def-lint.sh turns the check red` copies the real `tests/` dir, asserts the baseline passes, removes the guard-source line from a real backend-touching entrypoint, asserts the check exits 1 and names that file. Working tree is never mutated (operates on a `mktemp` copy; `trap … EXIT` cleans up). The sandbox-guard-check now covers 36 entrypoints (was 35 before this fix — the fixture work revealed `test-run-status-collector.sh` was missing the guard).

**AC4** — Proof lives in the suite, not a manual step: ✅  
All verification is in `tests/test-sandbox-guard.sh`.

---

## Scope Check

Delta on PILOT-62-auto over epic base 768badaf: 3 commits, 5 files.

| File | Change |
|------|--------|
| `docs/rule-ledger.yaml` | Added 5 entries (R-1102..R-1106) for SANDBOX_GUARD_SOP.md |
| `docs/sop/SANDBOX_GUARD_SOP.md` | New SOP; root cause + fixture discipline documented |
| `scripts/docs-identifier-check.sh` | Fix: accept `tests/` as a real ORCH_ knob source |
| `scripts/sandbox-guard-check.sh` | Fix: exclude full-comment lines from touch detection |
| `tests/test-docs-identifier-check.sh` | Test: cover the `tests/` ORCH_-knob case |

No product code, no RLS/auth/DB/TS surface. Shell + docs + YAML only. shellcheck -S warning rc 0.

---

## Verdict

**APPROVED** — all four ACs met, 12/12 sandbox-guard tests green, real-repo counter-proof non-vacuous. Releasing to Story Acceptance.
