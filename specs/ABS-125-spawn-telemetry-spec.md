# ABS-125 Design Spec — Tool/MCP/Skill Usage Telemetry per Spawn

**Ticket**: ABS-125 (epic ABS-114) · **Status**: accepted (architect review 2026-07-07:
#PATH_DECISION (b) APPROVED; implementation findings incorporated — F1 the extraction anchors to
the FIRST `"name"` after each `tool_use` type marker (a greedy match grabbed payload keys
literally called `name`, confirmed against real MCP transcripts), F2 parallel tool calls (multiple
blocks per message line) are all captured in order, F3 both trap cases are test-pinned,
F4 a Skill call records plain `Skill` (the sub-name is a payload), F5 the report resolves agent
defs via `ORCH_HARNESS_HOME` like the seam, F6 caveat: In Review spawns run under
`ORCH_REVIEW_TOOLS`, so the used-vs-granted list for system-architect mixes both toolsets — read
accordingly, F7 `find -maxdepth 2 -type f` by session UUID beats slug derivation (the CLI slug
transform maps `_`→`-`, undocumented — do not "optimize"), F8 the parse runs post-`wait`, the
transcript is flushed; any residual race lands on the `unavailable` path) · **Date**: 2026-07-07

## 0. Goal

Per completed spawn the runner records WHICH tools/MCC servers/skills the agent actually used —
aggregated counts per name plus the ordered tool sequence (operator refinement: the sequence
shows behavior patterns like "reads 6 documents before the first edit" = context-pack failure).
Data basis for ABS-123 mapping reviews and least-privilege pruning. Names/counts/order ONLY —
never arguments or payloads (log stays small, no ticket content leaks).

## 1. Capture path  `#PATH_DECISION`

- **(a) REJECTED — switch the seam to `--output-format stream-json`** and aggregate `tool_use`
  events in the watchdog/collector. Pros: documented output contract. Cons: rebuilds the seam's
  ENTIRE result handling (handoff extraction, session id, ABS-120 usage fields all parse the
  final-JSON shape today), touches the watchdog, and its resume interaction (does a resumed
  session re-emit prior events?) adds untestable-offline surface. Violates ADR-A-0010 for a
  telemetry feature that must degrade gracefully anyway.
- **(b) CHOSEN — parse the session transcript after the spawn ends.** The CLI writes
  `~/.claude/projects/<cwd-slug>/<session_id>.jsonl`; the runner already extracts the session id
  (A2). One `find` per completed spawn locates the file (override: `ORCH_TRANSCRIPT_DIR`, also
  the test seam); `tool_use` entries are extracted in FILE ORDER (JSONL is append-ordered — the
  sequence requirement is free). Zero seam change; the acknowledged cost is a path/format
  dependency on CLI internals — mitigated by design: ANY parse/lookup failure degrades to an
  empty-telemetry `TELEMETRY` line with `note=unavailable`, never a pipeline break. Foreign
  providers (Cursor seats, ABS-122) simply have no transcript → same graceful path.

Resume caveat (documented): a resumed session appends to the SAME transcript, so a resumed
spawn's telemetry covers the whole session so far, not the delta — acceptable for the
optimization questions this data serves (per-role used-vs-granted, pattern detection); a delta
cut would require persisting per-session offsets (rejected as premature).

## 2. Recording

Per completed spawn attempt (same site as ABS-120's SPAWN-USAGE):
- run.log: `TELEMETRY <ticket> <role> <status> note="Read=14 Bash=9 Skill=2 mcp__jira__get=3"`
  (aggregated `name=count`, sorted; empty note variant carries `unavailable`). Appends a new
  event KIND — existing TSV untouched.
- Sequence: `$ORCH_STATE_DIR/telemetry/<ticket>.<role>.<epoch>.seq` — one tool name per line in
  call order (separate file per spawn; the main run.log stays compact, ticket constraint).
- `ORCH_TELEMETRY=1` default; `0` disables both.

## 3. Report

`orchestrator-report.sh` gains a "Per role: tools used vs granted" section: used = aggregated
TELEMETRY counts per role; granted = the `tools:` frontmatter of the role def (harness namespace
resolution). Prints the "granted but never used" list per role (the least-privilege candidates)
and the raw usage counts. Skipped with a notice when no TELEMETRY lines exist.

## 4. Test plan

- fixture transcript (known tool_use order) + stub spawn with matching STUB_SESSION_ID and
  `ORCH_TRANSCRIPT_DIR` → TELEMETRY line with exact counts; sequence file matches the order
- no transcript / no session id → `TELEMETRY … unavailable`, spawn outcome unaffected
- `ORCH_TELEMETRY=0` → no TELEMETRY lines, no seq files
- report: used-vs-granted section lists an unused granted tool; graceful without telemetry
- no arguments/payloads: the seq/log contain tool NAMES only (assert a marker payload string
  from the fixture does NOT appear)
