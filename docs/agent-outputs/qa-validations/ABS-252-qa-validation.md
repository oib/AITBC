# QA Validation — ABS-252

**Ticket:** ABS-252 — Tracker-Adapter: `update body`/`body-file`
**Branch:** ABS-252-auto — commit `b6196b4`
**QAS run:** 2026-07-13
**Verdict:** APPROVED

---

## Suite Results (re-run independently)

| Suite | Count | Result |
|---|---|---|
| `tests/test-mock-tracker.sh` | 162 | PASS |
| `tests/test-jira-tracker.sh` | 123 (+1 SKIP live smoke) | PASS |
| `tests/test-tracker-adapter-lint.sh` | 2 | PASS |
| `generate-governor.sh --providers --check` | — | PASS (mirror parity) |
| `bash -n` on both adapters | — | PASS |

---

## AC Verification

**AC1 — `update <id> body <text>` / `body-file <path>` in both adapters: PASS**

- `scripts/mock-tracker.sh` lines 455–473: `body|body-file` branch in `cmd_update`, calls `set_body`.
- `scripts/jira-tracker.sh` lines 980–1042: `body|body-file` branch, wraps text as ADF, PUTs `{"fields":{"description":...}}`.
- Parity contract enforced by identical strings in both files: success `<id>: body updated`, error `update: body-file not found: $value`, error `update: unknown field '$field' (...|body|body-file)`.
- The jira suite greps the mock's own error strings — a future divergence fails a test.
- Independent smoke test confirmed: body replaced with `<angle>` bracket content, frontmatter intact, prior comment survived. Idempotent rewrite works. Missing-file and unknown-field errors fire correctly.

**AC2 — issue-enrichment uses `update … body-file` for append/rework: PASS**

- `harness/claude/agents/issue-enrichment.md` line 84+: "For append verdicts (and any AC-rework after enrichment): rewrite the matched ticket's body via `update <id> body-file`".
- `harness/claude/skills/issue-enrichment/SKILL.md` line 222: `"${TRACKER_CMD:-scripts/mock-tracker.sh}" update "$MATCH" body-file "$BODY_FILE"`.
- `generate-governor.sh --providers --check`: PASS — `agent_providers/claude_code/` mirrors the harness.

**AC3 — Adapter docs updated: PASS**

- `harness/claude/skills/tracker-ops/SKILL.md`: new "Rewrite a ticket BODY (`update … body-file`, ABS-252)" section with usage and inline vs body-file guidance.
- `profiles/neutral/adapters/task-tracking.md` line 43: `update_ticket` contract now mandates `body` / `body-file` support and the preserve-comments requirement.
- Both adapters' `--help` texts updated (verified via grep).
- `docs/sop/DEFINITION_OF_READY.md`: items 1 and 4 now correctly name `update … body-file` as an in-place edit; item 3 (`role:` hint) retains close-and-replace (label charset rejects `:`).

---

## System Architect LOW Nits (accepted, not bounced)

Both nits noted, non-blocking per system-architect's gate-results comment. Routing to docs seat for a follow-up ticket rather than holding this story:

1. `set_body` header comment does not name the `^## Comments$` boundary assumption it relies on.
2. DoR item 3 trailing clause "rides the same body-replacement path" is a stale antecedent.

## Mock `## Comments` Boundary Quirk

Accepted (pre-existing, per system-architect gate-results). No data loss; Jira binding immune by construction. QAS does not re-litigate.

---

## End State

- Branch `ABS-252-auto`, commit `b6196b4`, pushed to `origin/ABS-252-auto`. Working tree clean.
- All 287 adapter checks PASS. Governor mirror PASS. Smoke test PASS.
