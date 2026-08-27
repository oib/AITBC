# ABS-12 Design Spec — Iteration-Guard Hook

**Ticket**: ABS-12 (subtask ABS-20) · **Status**: accepted (decisions human-confirmed) · **Date**: 2026-07-03

Decision record for the mechanical loop-enforcement hook. It pins the three things the
implementation subtasks (ABS-21 script, ABS-22 tests, ABS-23 wiring) must not re-decide. The hook
is the **mechanical backstop** to the prompt-level rules delivered by ABS-11 — it does not replace
them or change them (per ABS-12 scope).

## 1. Bounce-marker convention

Gate agents (QAS, QAS-Design) already stamp every bounce comment with the literal marker
`Iteration N of M` (ABS-11). The guard counts, in a ticket's comments, every **comment block**
(not marker occurrence) that contains at least one match of:

```
Iteration [0-9]+ of [0-9]+
```

This ensures that a single comment body containing multiple marker mentions (e.g. "Previous attempt was Iteration 1 of 3; this is Iteration 2 of 3") counts as exactly one bounce, not two.

Comments are read **through the task-tracking adapter** (`mock-tracker.sh get <id>`, ADR-A-0006/0007)
— never by reading tracker files or a vendor API directly. Rendered comment shape (mock adapter):

```
### <timestamp> | kind: gate-results | actor: qas

... Iteration 2 of 3 ...
```

## 2. Cap source of truth  `#PATH_DECISION`

The cap **M is read from the most recent `Iteration N of M` marker** on the ticket; if no marker
parses, default **M = 3**. This keeps the cap co-located with the loop it governs and lets a
genuinely harder ticket declare a different bound (e.g. `of 5`) without a code change.

- **Chosen**: parse M from the marker; fall back to 3.
- **Rejected**: a hardcoded env var `ITERATION_CAP`. Loses per-ticket flexibility and splits the
  cap's source of truth away from the ticket the humans and agents actually read.

**Block condition** (matches ABS-11 "at N = 3, bouncing is FORBIDDEN"): let `P` = existing bounce
markers on the ticket; the bounce about to be posted is iteration `N = P + 1`. The guard **blocks
when `N ≥ M`** (equivalently `P ≥ M − 1`). So with the default cap, iterations 1 and 2 bounce
freely and the 3rd bounce is refused → human escalation.

> Off-by-one (human-confirmed): this yields **2 bounces then escalate** for a cap of 3. The
> alternative reading — allow 3 bounces, block the 4th — was considered and rejected in favour of
> matching ABS-11's literal "at N = 3, bouncing is FORBIDDEN."

## 3. Fail-open vs fail-closed  `#PATH_DECISION`

When the tracker is **unreachable**, or the **ticket id cannot be determined**, or no cap can be
parsed and the comment count is unreadable, the guard **exits 0 (fail-open)** and writes a labelled
warning to **stderr**.

- **Chosen — fail-open**: a flaky or offline tracker must not deadlock *every* agent handoff in the
  repo. The guard is a backstop; ABS-11's prompt-level rules remain the first line of defence when
  the backstop can't run. A missed cap during a rare outage is a soft, human-catchable failure.
- **Rejected — fail-closed**: blocking on any tracker hiccup turns "maybe looping" into "all work
  halted," trains operators to disable the hook, and a disabled hook protects nothing.

The warning is loud and prefixed (`iteration-guard: WARN ...`) so the skipped check is visible.

## 4. Interface

```
scripts/hooks/iteration-guard.sh <ticket-id>
```

- **exit 0** — under cap, proceed (also the fail-open path).
- **exit 2** — cap reached: block the bounce and escalate to a human (TDM/POPM).
- All human-readable output goes to **stderr only**; stdout stays empty. The exit-2 message names
  the ticket and the marker count, e.g. `iteration-guard: BLOCK ABS-42 — 2 prior bounces, cap 3 reached; escalate to human`.

## 5. Wiring sketch (for ABS-23)

- **Event**: a `PreToolUse` hook on **all Bash tool calls** (matcher: `"Bash"`). The hook reads stdin
  (JSON tool metadata), extracts `tool_input.command`, and enforces **only** on adapter gate bounce
  commands (`comment <TICKET>` plus `--kind gate-results` or `--kind handoff`). All other Bash calls
  (including those that mention a marker in a commit message or grep) return exit 0 immediately.
  The target ticket is the **last** `comment <TICKET>` in the command; commands with multiple distinct
  comment targets are blocked (exit 2) as ambiguous. Cap enforcement runs even when the marker is
  only in the runtime body (`--body "$VAR"`), not the literal command string.
- **Ticket id**: extracted from the bounce command only (no branch fallback in hook mode). If
  unextractable, fail-open (§3).
- **Registration file**: this repo keeps hooks in **`.claude/hooks-config.json`**, not
  `.claude/settings.json` (which exists only as `settings.template.json`). ABS-23 registers the
  guard there, additively — no existing hook or permission is removed or rewritten (ADR-A-0010).
  See "Open decisions" — the ticket text says `settings.json`.

**Feasibility boundary**: the guard can only intercept a bounce expressed as a tool call the harness
sees (an adapter Bash call, or a matchable MCP call). A gate agent that "bounces" by merely
returning prose is not mechanically interceptable — which is exactly why the ABS-11 prompt-level
rules stay in place as layer one. This is a known limitation, not a defect.

## Resolved decisions (human-confirmed 2026-07-03)

1. **Fail-open vs fail-closed** (§3) — **fail-open + loud stderr warning.** ✅
2. **Cap off-by-one** (§2) — **block when `N ≥ M`** (2 bounces then escalate at cap 3), matching
   ABS-11's "at N = 3 forbidden." ✅
3. **Registration file** (§5) — **`.claude/hooks-config.json`** (where hooks actually live); the
   ticket's `.claude/settings.json` wording is superseded for this repo's layout. ✅

## Amendment (2026-07-03, post-review)

Implementation corrections from PR #9 review and PR #10 follow-up (matcher fires on tool name only;
ticket from bounce command; per-comment-block counting; `TRACKER_CMD` shapes; narrow hook trigger to
`comment` + `gate-results|handoff` with last-ticket wins and multi-target block). Details in PR #10
body and `.claude/README.md`.

### Amendment 2 (2026-07-03, PR #10 review follow-up)

Three hardening fixes from the PR #10 review:

1. **Sibling matchers reactivated.** The same tool-name-only matcher defect (finding #1) left the
   `git commit`, `git push` (block-to-`main`, block-uncommitted, behind-warn) and `gh pr create`
   hooks in `hooks-config.json` permanently inert. All now use matcher `"Bash"` and re-derive the
   command from stdin via the shared `scripts/hooks/extract-bash-command.sh` helper (which the guard
   also uses). The two `git push` guardrails now hard-block with **exit 2** (they previously used
   the non-blocking `exit 1`, so the "BLOCKER" label was never truthful).
2. **Comment-block parser no longer requires a blank line** between a `### ` comment header and its
   body. The `### ` line is consumed by its own rule, so every other line is body regardless of
   separators — an adapter that renders `### header` immediately followed by the marker still has its
   bounces counted (the mock adapter emits the blank line; real adapters need not).
3. **Adapter resolution accepts a script-file path *with arguments*** (a 4th shape). A file first
   token is run via `bash` (so an unset `+x` bit does not silently fail-open); otherwise a PATH
   command is used. Fail-open preserved only for a genuinely unresolvable adapter.
