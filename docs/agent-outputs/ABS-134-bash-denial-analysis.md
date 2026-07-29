# ABS-134 — Root-Cause: uneinheitliche Bash-Denials in Headless-Seats

- **Type**: Spike / Enabler (parent ABS-130)
- **Seat**: be-developer (headless)
- **Date**: 2026-07-08
- **Befund**: Report Befund 3, Run ABS-126
- **Status**: Root cause **found and reproduced live** (executed experiments below)

---

## TL;DR

The denials are **not** caused by command shape, prefix-matching, compound
segments, multi-line `--body` arguments, cwd correctness, or the ABS-123
`--allowedTools Skill` flag. Every one of those hypotheses is **refuted by
direct, executed experiment** (§3).

**Root cause: a fresh-spawn permission-initialization race.** Under
`--permission-mode dontAsk`, the **first Bash tool call(s)** of a fresh
(non-resumed) headless spawn are silently **denied** because the per-ticket
worktree's permission allow-list (`.claude/settings.local.json`) is **not yet in
effect** at that instant. `.claude/settings.local.json` is **gitignored /
untracked**, so a runner-provisioned worktree (`git worktree add tmp/<ticket>-work`,
ABS-111 C9) is created **without** it; the file is provisioned out-of-band and
**races** the agent's first tool call. Once the allow-list is in effect,
subsequent calls — **including byte-for-byte replays of the denied commands** —
succeed.

This is why the denial correlated with *role* in Befund 3 without being *caused*
by role: it hits whichever seat issues an adapter (`scripts/jira-tracker.sh`),
`git push`, or `bb` command as (one of) its **first** Bash actions. Seats that
front-load read-only Bash exploration (bsa, qas) warm past the window and never
notice; the same `po-agent` role appears on **both** the affected (prioritization,
fresh) and unaffected (acceptance, resumed/warmed) sides — the decisive tell that
the discriminant is **spawn state, not role**.

---

## 1. Context (Befund 3)

po-agent, be-developer, system-architect and rte could **not** run adapter
commands (`scripts/jira-tracker.sh comment/transition`), `git push`, or `bb`
("Bash denied"), although the main-tree allowlist covers those commands and the
telemetry shows **successful** Bash calls from the same seats (po-agent Bash=3,
SA Bash=38). bsa, qas and the po-agent **acceptance** seat could run the same
adapter writes.

Hypotheses to test (from the ticket):
- H1 multi-line `--body` arguments fail prefix-matching
- H2 compound segments (`&&`, pipes) fail matching
- H3 cwd-dependent settings resolution
- H4 `--allowedTools` (ABS-123 Skill) interaction
- H5 fresh-spawn vs. `--resume` differences

---

## 2. Method

This spike was run **from inside an affected seat** (be-developer, headless,
`--permission-mode dontAsk`, worktree cwd `tmp/ABS-134-work`). The seat
reproduced the denial *on its own opening tool calls*, so the "test spawn" is the
live seat itself — the strongest possible repro. Each hypothesis was then
isolated by varying one factor at a time and re-executing.

---

## 3. Repro Matrix (all rows EXECUTED)

| # | Command (shape) | When in session | Result | Isolates |
|---|---|---|---|---|
| 1 | `cd <wt> 2>/dev/null && pwd && echo … && ls knowledge/ 2>/dev/null && … && ls -la .claude/settings*.json` | **1st call** | **DENIED** | baseline |
| 2 | `cd <wt> 2>/dev/null && … && find . -name '…' && … \| head` | **2nd call** | **DENIED** | baseline |
| 3 | `pwd` | 3rd call | allowed | simple single |
| 4 | `ls <abs-path>` | 3rd call | allowed | single, abs path |
| 5 | `ls <abs-path> && echo done` | later | allowed | H2 compound `&&` |
| 6 | `ls <abs-path> 2>/dev/null` | later | allowed | redirect |
| 7 | `cd <abs-path>` | later | allowed | bare cd |
| 8 | `echo "line one\nline two"` (real newline) | later | allowed | H1 multi-line body |
| 9 | `cd <wt> 2>/dev/null && pwd` | later | allowed | H3 cd+redirect prefix |
| 10 | `find <abs> -maxdepth 2 -name '…'` | later | allowed | `find` verb |
| 11 | `ls knowledge/` (relative) | later | allowed | relative path after no-cd |
| 12 | `ls -la <abs>/.claude/settings*.json` | later | allowed | glob over `.claude` |
| 13 | `find . -name 'jira-tracker.sh' \| head` | later | allowed | H2 relative-dot + pipe |
| **14** | **verbatim replay of row 1 (identical string)** | later | **allowed** | **decisive: content vs. state** |
| **15** | **verbatim replay of row 2 (identical string)** | later | **allowed** | **decisive: content vs. state** |

`<wt>` = `/Users/.../tmp/ABS-134-work`.

**Decisive rows 14–15**: the *exact same command strings* that were denied as the
opening calls (rows 1–2) execute successfully later in the same session. The only
variable that changed is **session/permission state** — proving the denial is a
function of *when* the call fires (fresh-spawn initialization window), not *what*
the call contains.

---

## 4. Hypothesis verdicts

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | multi-line `--body` fails prefix-match | **REFUTED** | row 8 passes; rows 14–15 (same strings) pass |
| H2 | compound `&&` / pipe segments fail | **REFUTED** | rows 5, 13 pass; every sub-segment of rows 1–2 passes in isolation |
| H3 | cwd-dependent settings resolution | **PARTIAL / mechanism** | true underlying cause is the worktree allow-list race (§5); cwd was correct, the *file* was the problem |
| H4 | `--allowedTools Skill` (ABS-123) interaction | **REFUTED as discriminant** | affected/unaffected split does not map to Skill-in-tools (§5.1) |
| H5 | fresh-spawn vs. `--resume` | **CONFIRMED (primary)** | denial only on opening calls of a fresh spawn; resumed/warmed seats unaffected; same po-agent role on both sides |

### 4.1 Why H4 (Skill / `--allowedTools`) is refuted

`tools:` frontmatter per role (`harness/.claude/agents/*.md`):

| Seat | Skill in tools? | Befund-3 outcome |
|---|---|---|
| po-agent | **no** | **affected** (prioritization) / unaffected (acceptance) |
| be-developer | yes | affected |
| system-architect | yes | affected |
| rte | yes | affected |
| bsa | no | unaffected |
| qas | **yes** | **unaffected** |

`po-agent` (no Skill) is affected while `qas` (has Skill) is unaffected — the
`--allowedTools "Skill"` flag (`orchestrator-spawn-claude.sh` lines 208–217) does
**not** partition the two groups. It is not the cause.

---

## 5. Root cause (mechanical)

1. **The allow-list is gitignored.** `git check-ignore` resolves
   `.claude/settings.local.json` against the global ignore
   `**/.claude/settings.local.json`; `git ls-files --error-unmatch` confirms it is
   **untracked**.
2. **Fresh worktrees don't get it.** The runner provisions each implementer spawn
   its own worktree via `git worktree add tmp/<ticket>-work`
   (`scripts/orchestrator.sh` `ensure_worktree()`, lines 1977–2030). `git worktree
   add` only materializes **tracked** files → the new worktree has **no**
   `.claude/settings.local.json` at creation time. `ensure_worktree()` contains
   **no step** that copies it in.
3. **The file arrives late.** The observed worktree file
   (`tmp/ABS-134-work/.claude/settings.local.json`) has a timestamp (00:32)
   **after** worktree creation — it is provisioned out-of-band, **racing** the
   spawn's first tool call.
4. **dontAsk denies during the window.** `orchestrator-spawn-claude.sh` launches
   `claude -p … --permission-mode dontAsk` (line 204). In dontAsk mode a tool call
   not covered by any *loaded* allow rule is **silently denied** (no prompt). Until
   the allow-list is in effect, the first Bash call(s) are denied. The main
   checkout's `.claude/settings.local.json` grants a bare `"Bash"` (all bash), so
   once resolved, everything passes (rows 3–15).

The runner even reasons about the allow-list at the **main-checkout** path
(`$ORCH_STATE_ROOT/.claude/settings.local.json`, `orchestrator.sh` line 322, in
`compute_config_generation`) while the spawn's cwd is the **worktree** — the
config-generation comment at lines 293–299 already records a symptom of this same
class ("a pre-allowlist-fix dev session stayed tracker-denied on every resume
while fresh spawns worked").

### 5.1 Residual uncertainty (stated honestly)

Which component writes the worktree-local `.claude/settings.local.json` (a
SessionStart hook, harness-sync, or the runner) was not fully traced from this
seat. It does not change the root cause or the fix: whichever component provisions
it, it currently does so **without a happens-before guarantee** relative to the
spawn's first tool call. **Verification step** for the fix owner: instrument
`ensure_worktree()` / the spawn seam to log the worktree's
`.claude/settings.local.json` mtime vs. the spawn launch time across a live run,
and confirm the denial window closes once provisioning is synchronous.

---

## 6. Fix recommendation

### Fix A (primary — closes the race at its source)

Provision the worktree's `.claude/settings.local.json` **synchronously inside
`ensure_worktree()`**, immediately after a successful `git worktree add` and
**before** the lock is released / the spawn is launched.

- **File**: `scripts/orchestrator.sh` — `ensure_worktree()` (lines 1977–2030),
  after the `git worktree add` calls (lines 2004 / 2021 / 2023), before `rmdir
  "$wlock"` (line 2027).
- **Change (~4–6 lines)**: copy `$ORCH_STATE_ROOT/.claude/settings.local.json`
  into `$wt/.claude/` when the source exists, else render it from the tracked
  `$ORCH_STATE_ROOT/.claude/settings.template.json`. Guarded (`mkdir -p
  "$wt/.claude"`; skip if source missing).
- **Why safe**: identical file content → **no** change to permission semantics or
  least-privilege; it only makes the *existing* grant present at turn 1. Targets
  the true root cause (a gitignored file absent from a fresh worktree).
- **Kill-switch**: fits the ABS-111 "default-on seam + `=0`" convention
  (`ORCH_WORKTREE_SETTINGS=0`).

### Fix B (optional hardening — defense in depth)

Make the CLI-side allow-list authoritative at turn 1, independent of file
discovery: extend the `--allowedTools` construction to pass the seat's declared
tools, not only `Skill`.

- **File**: `scripts/orchestrator-spawn-claude.sh` — lines 208–217 (the
  `case "$SEAT_TOOLS" in *Skill*)` block).
- **Caveat**: requires a **live** check of `--allowedTools` merge-vs-replace
  semantics against the settings allow-list before adoption; do not ship blind.
- Does not over-grant (settings already grant bare `Bash`).

**Recommended**: ship **Fix A** (root cause, tiny, semantics-preserving). Treat
Fix B as optional hardening pending the merge-semantics check.

### Out of scope for this spike

The fix itself is **not** shipped here: it touches the production runner /
permission seam and is >10 lines including guards + kill-switch + tests, so it
exceeds the "<10 Zeilen darf direkt mitgeliefert werden" allowance. Delivered as
recommendation + follow-up (below), for System-Architect review + a live-spawn
verification (§5.1) that cannot be run from this headless seat.

---

## 7. Follow-up ticket (dedup gate applied)

Dedup gate (`duplicate-detection` skill) run before proposing the follow-up:

- **Searched** (searchable store = mock tracker `scripts/mock-tracker.sh search`):
  `bash denial`, `permission race`, `settings.local`, `worktree`, `dontAsk`,
  `allowlist`, `adapter denied` — **no matches** (store holds only `DEMO-*`
  fixtures; the live Jira store is not reachable from the be-developer seat, which
  carries no tracker MCP).
- **Verdict**: `create` (rule 5 — no identical/similar ticket in the searchable
  store). Live-tracker creation is out of this seat's tools → routed to the
  issue-enrichment / PO flow.

**Proposed story** (relates-to ABS-134, ABS-130; touches ABS-111 C9):

> **Provision `.claude/settings.local.json` into the per-ticket worktree before
> spawn to close the fresh-spawn Bash permission race (dontAsk).**
> Root cause per ABS-134: the gitignored allow-list is absent from a fresh
> `git worktree add` and provisioned out-of-band, racing the first tool call;
> under `--permission-mode dontAsk` the first Bash call(s) are denied. Implement
> Fix A (§6) in `ensure_worktree()`; add a regression test asserting the
> worktree contains `.claude/settings.local.json` before spawn; optionally
> evaluate Fix B after the merge-semantics check.
> AC: fresh-spawn seats can run adapter/`git`/`bb` on their first Bash call; the
> ABS-126 Befund-3 denial does not recur in a live run.

---

## 8. Acceptance criteria coverage

- [x] Analysis doc with repro matrix and **named root cause** (fresh-spawn
      allow-list provisioning race), with the competing hypotheses explicitly
      refuted (§3–§5).
- [x] At least one **executed** repro experiment documented — 15 executed rows,
      incl. the decisive verbatim replays (rows 14–15).
- [x] Recommendation: concrete fix path incl. affected files
      (`scripts/orchestrator.sh` `ensure_worktree()` lines 1977–2030; optionally
      `scripts/orchestrator-spawn-claude.sh` lines 208–217) — §6.

---

## References

- Report Befund 3 (Run ABS-126)
- `.claude/settings.local.json` (gitignored, untracked; bare `"Bash"` allow)
- `scripts/orchestrator-spawn-claude.sh` — `--permission-mode dontAsk` (204),
  `--allowedTools Skill` (208–217), `ORCH_SPAWN_CWD` worktree cwd (219–228)
- `scripts/orchestrator.sh` — `ensure_worktree()` (1977–2030),
  `compute_config_generation` (293–327)
- `knowledge/orchestrator-hardening-abs-111.md` — A2 fresh-vs-resume, C9 worktrees
- ADR-A-0002 (fresh subagent per task) — resume scope = task, ends at acceptance
