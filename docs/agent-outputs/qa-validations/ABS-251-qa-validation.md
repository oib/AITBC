# QA Validation — ABS-251

**Ticket**: ABS-251 — Spawn-Seam: argv-size-gated `--agent` fallback (Windows CreateProcess ~32KB limit)
**Branch**: ABS-251-auto
**Commit**: 8e9aad0
**Files reviewed**: `scripts/orchestrator-spawn-claude.sh` (+30 lines), `tests/test-orchestrator.sh` (+78 lines)
**QAS run**: 2026-07-13
**Verdict**: APPROVED

---

## AC Verification

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | Size gate `ORCH_AGENTS_ARG_MAX` (default 24000), fallback to `--agent`, configurable both ways | PASS | 5 assertions: oversized omits `--agents`, adds `--agent bigrole`; raised gate goes inline; lowered gate forces fallback for small def |
| AC2 | Tool-narrowing parity — read-only seats stay read-only in the fallback path | PASS | 3 assertions: write-free `ORCH_TOOLS` → `--disallowedTools Write,Edit,NotebookEdit`; write-granting override → no denial; no override → no denial |
| AC3 | Spawn-seam stub test: big def → fallback flags logged to stderr | PASS | `assert_contains ... "ORCH_AGENTS_ARG_MAX"` on stderr; real `orchestrator-spawn-claude.sh` + fake claude binary |
| AC4 | macOS/Linux path under the gate byte-identical (no fallback, no narrowing, seam silent) | PASS | 4 assertions: `--agents` present, `--agent smallrole` present, no `--disallowedTools`, no fallback notice on stderr |

All 4 ACs met. 12/12 ABS-251 assertions PASS.

---

## Test Suite Results

Three independent runs of `bash tests/test-orchestrator.sh`:

```
Total:  663   Passed: 645   Failed: 18
```

Delta vs. clean baseline (8e9aad0 stashed): +12 tests, all passing; zero new failures.
The 18 failures are pre-existing, unrelated to this diff:
- 2 provenance harness-path FAILs (self-hosting mode: suite run from `tmp/ABS-251-work`, not the stable checkout)
- 16 label-propagation/model-label fixture tests (environment-specific)

None touch the spawn seam.

---

## Code Review Notes

- New `elif` slots into the existing argv-assembly ladder after `ORCH_RESUME_SESSION_ID` and before the inline `--agents` branch — minimal diff, no drive-by changes.
- `ORCH_AGENTS_ARG_MAX` follows the existing `ORCH_*` override convention; documented in the file header.
- Fallback notice goes to stderr — observable by the orchestrator without polluting stdout.
- `case "${ORCH_TOOLS:-}"` pattern correctly classifies write-free, write-granting, and absent overrides.
- Accepted limitations (match consumer BUSCH PR #18 scope, documented in-file):
  1. On-disk `--agent` path does not receive ABS-174 commons prepending — degraded spawn beats crashed spawn.
  2. Narrowing covers `Write,Edit,NotebookEdit` only, not `Bash` — matches the realistic reviewer toolset intent.

No new patterns introduced; no ADR warranted.

---

## Gate Checklist

- [x] AC1 — size gate + configurable fallback: PASS
- [x] AC2 — tool-narrowing parity: PASS
- [x] AC3 — stub test with fallback logging: PASS
- [x] AC4 — byte-identical under the gate: PASS
- [x] Full test suite: 663/645/18 — zero new failures
- [x] Code review: pattern-compliant, minimal diff, in-file documentation adequate
- [x] Known limitations documented and accepted
