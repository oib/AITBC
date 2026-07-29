# ABS-162 — Decision: What `mcp__…__*` tool grants mean in headless spawns

**Date:** 2026-07-08 · **Parent:** ABS-152 (AC-6, AC-7) · **Aligns with:** ABS-123 (headless-skill audit)
**Author seat:** be-developer · **Scope:** decide + document; reconcile grants to reality. Enabling MCP
in the headless loop is explicitly **out of scope** (per epic ABS-152).

---

## Decision (TL;DR)

**`mcp__…__*` tool grants are INERT in headless orchestrator spawns.** They do nothing in the
headless lane. They retain latent meaning **only** in interactive sessions (Claude Code / an IDE)
under a profile that both (a) substitutes the MCP server placeholder with a real server name and
(b) actually connects that MCP server.

Because the grant is inert headless, the headless lane's tracker access runs **exclusively through
`$TRACKER_CMD`** — the task-tracking adapter (default `scripts/mock-tracker.sh`), invoked via the
`Bash` tool, per **ADR-A-0007** (all external systems live behind neutral adapter interfaces). No
headless seat ever reaches the tracker via MCP.

We **do not delete** the grants (that would regress the interactive path — a breaking change the
ticket's guardrail annotation explicitly excludes: "approval boundaries: none"). Instead we
**substitute the bare grant with an explicit annotation** in each affected agent definition that
states the grant is interactive-only and that headless tracker access is via `$TRACKER_CMD`.

---

## Why inert (evidence, from ABS-123)

The ABS-123 audit (`docs/agent-outputs/ABS-123-headless-skill-audit.md`) ran real seam spawns via
`scripts/orchestrator-spawn-claude.sh`. Two independent facts make the grant inert headless:

1. **No MCP server is connected in the headless spawn.** In probe P2a (a real `qas` seat spawn), the
   grant `mcp__linear-mcp__*` was "passed through as a literal, matches no server →
   ineffective" — the seat self-reported only `Read, Bash`. The grant string names a server that is
   not attached, so it resolves to nothing.
2. **The neutral/mock profile never substitutes the placeholder.** `linear-mcp` /
   `confluence-mcp` are only replaced when a profile binds a real MCP server (e.g.
   `saw-stack` → Linear MCP). In the shipped neutral profile (`task-tracking: mock`) the token stays
   literal, so the grant is a dead string even before the "no server connected" point.

The `tools:` frontmatter is a **hard allowlist** (ABS-123 probe P5): what is not needed is simply
never exercised. Headless seats already carry `Bash`, which is how they run `$TRACKER_CMD`. The MCP
grant is therefore redundant weight in the headless lane, not a capability.

Contrast — where the grant **is** meaningful: an interactive Claude Code / IDE session where the
user has configured a real MCP server (`.claude/settings.local.json` `mcpServers`, `.gemini/settings.json`,
`.cursor/mcp.json`, or Codex's native MCP) under a profile that substitutes the placeholder. That is
outside the headless orchestrator loop and outside this ticket's scope.

---

## Reconciliation applied

### AC-2a — headless `$TRACKER_CMD` reliance made explicit

- The affected agent definitions already describe tracker reads/writes as "adapter via
  `$TRACKER_CMD`, default `scripts/mock-tracker.sh`" in their autonomous-reconciliation sections,
  and the orchestrator itself is adapter-only (`docs/sop/ORCHESTRATOR_SOP.md`, ADR-A-0007).
- This decision makes that reliance **explicit at the top of each affected agent definition** via a
  one-line annotation immediately under the H1 (see AC-2b).

### AC-2b — inert grant substituted (not deleted)

**Edit target = the work-product source, not the generated live tree.** Under self-hosting (ABS-94),
the live `.claude/` is `generate-governor.sh` output materialized from the pinned release tag
(`.governor-tag` = `v2.21.2`, extracted from `harness/.claude/**` at that tag) and is drift-guarded
(`tests/test-harness-parity.sh` → `generate-governor.sh --check`). Hand-editing live `.claude/`
would fail the drift guard. The editable source for the Claude tree is therefore **`harness/.claude/`**;
the annotation ships into the live `.claude/` at the next promotion (ABS-95, `promote-release.sh`),
which is a release action, not this ticket's.

A single annotation line was added under the H1 of every Claude agent definition that carries an
`mcp__…__*` grant, in the source tree **`harness/.claude/agents/`**:

| Agent def | Grant present | Annotated |
|-----------|---------------|-----------|
| `qas.md` | `create_comment`, `update_issue`, `list_comments` | ✅ |
| `qas-design.md` | `create_comment`, `update_issue`, `list_comments` | ✅ |
| `tdm.md` | `mcp__…LINEAR__*`, `mcp__…CONFLUENCE__*` | ✅ |
| `po-agent.md` | `mcp__…LINEAR__*` | ✅ |
| `issue-enrichment.md` | `mcp__…LINEAR__*` | ✅ |
| `bsa.md` | `mcp__…LINEAR__*` | ✅ |

The annotation states the grant is interactive-only and inert headless, and that headless tracker
access is via `$TRACKER_CMD` (Bash, ADR-A-0007). This is a **substitute**, not a delete: the grant
remains for the interactive path, but its true meaning is now documented in-place.

### AC-3 — mirror parity across the four provider trees

| Provider tree | Carries the grant headless? | State after ABS-162 |
|---------------|-----------------------------|---------------------|
| `.claude/` | Yes — in agent `tools:` frontmatter (the headless engine is `claude -p`) | Annotated at the source `harness/.claude/agents/` (live `.claude/` is generated from the pin; the annotation lands there at the next promotion). Parity guard `tests/test-harness-parity.sh` passes. |
| `.cursor/` | No agent grant; MCP is IDE/interactive config (`.cursor/mcp.json`) | `.cursor/rules/31-mcp-integration.mdc` gained a "Headless orchestration" note stating MCP is inert headless and `$TRACKER_CMD` is used. Edited directly (not governor-generated). |
| `.gemini/` | No agent-frontmatter grant; `mcp__…` appears only as *production/interactive* adapter examples inside skills | Consistent by construction — no headless MCP claim to reconcile. |
| `.codex/` | No `mcp__…` grant in the `.toml` agent defs at all | Consistent by construction — nothing to reconcile. |

Parity invariant established: **no provider tree claims MCP is available in the headless
orchestrator lane; all headless tracker access is via `$TRACKER_CMD` (ADR-A-0007).** Only the Claude
tree required in-file annotation (in its `harness/.claude/` source) because it is the only tree whose
spawned seats carry the grant; the other three are already consistent. `harness/` contains only
`.claude/`, so no other tree has a generated/source split.

---

## References

- ABS-123 — `docs/agent-outputs/ABS-123-headless-skill-audit.md` (probes P2a, P5; core finding that
  the grant is passed as an unmatched literal).
- ADR-A-0007 — `adrs/agentic/ADR-A-0007-adapter-model.md` (adapter-only external access; the mock
  task-tracking adapter is the reference).
- Orchestrator adapter-only invariant — `docs/sop/ORCHESTRATOR_SOP.md`.
- Capabilities/profiles (why the placeholder is unsubstituted under `mock`) —
  `knowledge/capabilities-and-profiles.md`.
