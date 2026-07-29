---
type: concept
resource: scripts/orchestrator.sh
tags: [orchestrator, workflow, performance, observability]
timestamp: 2026-07-06
---

# Orchestrator hardening (ABS-111)

Epic ABS-111 hardens the event-loop Coordinator (`scripts/orchestrator.sh` + the spawn seam
`scripts/orchestrator-spawn-claude.sh`) for real live runs: async spawns so concurrency has
effect, warm session-resume within a task, dependency and worktree isolation gates, per-seat
budgets, and a structured event log. Every new behavior is a default-on seam with an `=0`
kill-switch, so the legacy path is one env var away. This concept summarizes the operating model;
the operational runbook is [`docs/sop/ORCHESTRATOR_SOP.md`](../docs/sop/ORCHESTRATOR_SOP.md).

## Operating model

### Async spawns (A1)

Live spawns run as background jobs. The attempt→retry→record sequence runs in a subshell that
holds the ticket's single-flight lock for its lifetime; `live_spawn_count` reaps dead pids so
`ORCH_MAX_CONCURRENT` caps the number of **in-flight** background jobs (the legacy synchronous
scheduler kept at most one spawn in flight, so the cap was inert). On `--once` and every loop-exit
path the runner drains in-flight spawns (`wait_for_spawns`) so tests keep synchronous
post-conditions. `ORCH_ASYNC_SPAWNS=0` restores the one-at-a-time scheduler.

### Session resume until acceptance (A2)

A session store under `work/.orchestrator/sessions/` keeps one file per `(ticket, role, status)`
holding the session id parsed from the CLI JSON result. The same session is **resumed** on rework
bounces and re-reviews (seam env `ORCH_RESUME_SESSION_ID`, which makes the seam call
`claude -p --resume <id>` and omit `--agents`/`--agent`). A **retry after a failed attempt is
always fresh** — resuming a just-failed session would repeat the failure. The resume scope is the
task, and the task ends at **acceptance**: entering `Merging`/`Done` deletes the ticket's stored
sessions (`clear_sessions`), so no context bleeds across task boundaries. This is the ADR-A-0002
"fresh subagent per task" reading precise about the task boundary (see the 2026-07-06 amendment).
`ORCH_SESSION_RESUME=0` disables resume.

### Handoff repair + status evidence (A2c / C7)

A spawn that exits cleanly but emits no parseable handoff is **repaired**: the runner resumes the
same session with a 4-turn budget and asks for only the `## Handoff` block (`INTENT
REPAIR-HANDOFF`). If there is still no handoff but the ticket has **demonstrably left** its spawn
status, the runner **synthesizes** a handoff from that status evidence (`INTENT SYNTH-HANDOFF`)
instead of recording a phantom `SPAWN-CRASH` — the fix for committed work being mislabeled as a
crash in live run 1.

### Gates: depends_on (C8) and worktrees (C9)

- **depends_on gate.** At implementation entry (`Ready for Development`, `Design`) a ticket whose
  `depends_on` names a not-`Done` ticket **rests** (`INTENT DEPENDS-WAIT`, note `unmet=<dep>:<status>`);
  the reconcile sweep re-derives the spawn once the dependency lands — no marker, no crash.
  `ORCH_DEPENDS_GATING=0` disables.
- **Runner-provisioned worktrees.** Each implementer spawn (`Ready for Development`) gets its own
  git worktree `tmp/<ticket>-work` on branch `<ticket>-auto`, created by the runner under a
  serialized `git worktree add` lock and handed to the seam as `ORCH_SPAWN_CWD` (precedence over
  `ORCH_TARGET_REPO`). Isolation is infrastructure, not agent discipline — a spawn physically
  cannot touch the main checkout (where the running loop lives). Worktrees must live **inside** the
  repo (headless file-tool sandbox). `ORCH_WORKTREE_SPAWNS=0` disables.

### Per-seat overrides (A3 / B6)

`ORCH_MAX_TURNS_<ROLE>` and `ORCH_MODEL_<ROLE>` override the global turn ceiling and model per
seat (role uppercased, dashes→underscores, e.g. `ORCH_MAX_TURNS_ISSUE_ENRICHMENT=120`,
`ORCH_MODEL_QAS=sonnet`). They beat the role frontmatter and the global `ORCH_MAX_TURNS`/`ORCH_MODEL`.

### Observability: run.log (D11 / D12)

`work/.orchestrator/run.log` is an append-only TSV event stream — columns `ts, kind, ticket,
role, to, note` — mirroring every intent and log line with a UTC timestamp; safe under concurrent
background spawns (one `printf` per line). Runner log lines are timestamped. Spawn **stderr** is
captured to a file and **kept on failure** for diagnosis (previously discarded). `SKIP-UNLABELLED`
is emitted to stdout once per ticket per run (the run.log still records every occurrence) so the
reconcile sweep no longer spams one skip line per resting Backlog ticket per sweep.

### Jira adapter + handoff decode (C10)

The Jira adapter migrated its search to `/rest/api/3/search/jql` (the legacy `/rest/api/3/search`
returns 410 after Atlassian CHANGE-2046). The literal-`\n` artifact in Jira handoff comments is
fixed at its **root, tracker-agnostically**: in the runner, `json_unescape` decodes `\n`/`\t`/`\"`
in the extracted handoff (`extract_handoff_from_result`) before it is handed to any adapter. The
adapters then post the already-decoded body **verbatim** — `adf_wrap` splits real newlines into ADF
paragraphs, and a legitimate literal backslash-n is left untouched (no second decode downstream).

### Context sequence + Context Packs (B4 / B5)

Every orchestrator seat def (`harness/.claude/agents/`) now carries a mandatory
**"Context Sequence (MANDATORY, ADR-A-0003)"** section: ticket + Context Pack → `knowledge/index.md`
→ `graphify-out/` → deliberate file reads ("graph before grep"). `issue-enrichment` writes a
`## Context Pack` block (≤ ~2 KB, **references not full text**: ADR key-sentences with paths,
pattern paths, code references derived from `graphify-out`, guardrails) into every ticket, keeping
the spawn packet under its 32 KB cap.

## codebase-memory MCP evaluation (B5)

Sober current state: **no `codebase-memory` MCP is configured in this repo.** The existing
alternative is the `knowledge/` OKF bundle plus the graphify code graph in `graphify-out/`, and
that alternative is now **wired into the agent defs** (the mandatory context sequence + the
enrichment Context Pack duty above). Recommended hygiene: run `graphify update .` (AST-based, no
API cost) before a live run so the graph is fresh. A dedicated MCP evaluation stays a **follow-up**
to open only if `knowledge/` + graphify prove insufficient in practice — it is not adopted now.

## Rules and constraints

- Every ABS-111 seam is **default-on**; the matching `ORCH_*=0` env var restores legacy behavior.
- Retries are always fresh; only rework/re-review/handoff-repair resume a session.
- Sessions are deleted at acceptance (`Merging`/`Done`) — no cross-task context bleed.
- Worktrees live inside the repo (`tmp/<ticket>-work`); external sibling paths fail the sandbox.
- The stdout `INTENT ...` shape is frozen (tests assert on it); timestamps go to `run.log`.

## Related

- [[ticket-lifecycle-and-statuses]] — the status→role map the runner drives spawns from.
- [[loop-termination]] — the bounce-cap backstop that coexists with session resume.
- ADR-A-0002 (`adrs/agentic/ADR-A-0002-fresh-subagent-execution.md`) — 2026-07-06 amendment: the
  task boundary is acceptance; intra-task resume is conformant.
- ADR-A-0003 (`adrs/agentic/ADR-A-0003-context-minimization.md`) — the context sequence the seats
  now enforce.
- Runbook: `docs/sop/ORCHESTRATOR_SOP.md` (open only when operating the runner).
- Source: `scripts/orchestrator.sh`, `scripts/orchestrator-spawn-claude.sh` (open when the task
  names them).
