# Agent-Def Overlay Guide

**Shipped in**: ABS-258 (epic ABS-245, ADR-A-0022)

A consuming project can extend a shipped agent def without editing it, by adding
a project-owned `.agentic/overrides/agents/<role>.append.md` file. The
orchestrator appends this overlay to the role prompt at spawn time. The def file
on disk stays byte-identical to upstream, so migration classifies it **REPLACE**
and the project keeps receiving upstream improvements — while the overlay survives
every migration untouched.

---

## When to Use This

You want to add project-specific rules, test commands, or conventions to a
shipped agent def (e.g. point the QAS seat at your specific test commands, or
add a project section to the BE developer prompt). The change is *additive* — you
are appending to the role, not replacing it.

If you edit the def file itself the customization becomes drift: every future
migration reports a CONFLICT and you have to re-apply the same section by hand
indefinitely.

**Use an overlay when the change is additive. Use `project_owned_exceptions` only
when you have genuinely rewritten the def and want to freeze your version.**

See the decision table in [BOILERPLATE_MIGRATION_SOP.md §3.3](../sop/BOILERPLATE_MIGRATION_SOP.md)
and the wholesale-fork path in [CONSUMER_FORK_DECLARATION_GUIDE.md](CONSUMER_FORK_DECLARATION_GUIDE.md).

---

## Quick Start

### Step 1 — Create the overlay file

```bash
mkdir -p .agentic/overrides/agents
# <role> is the def's basename without the .md extension.
# Example: .claude/agents/qas.md -> qas.append.md
$EDITOR .agentic/overrides/agents/qas.append.md
```

Write plain markdown. Do not add YAML frontmatter — it is stripped and ignored
(see [Limits](#limits)).

Example overlay for the QAS seat:

```markdown
## Project test commands

Run these to validate ACs before marking a story PASS:

- Unit tests: `npm test`
- Integration: `npm run test:integration`
- Linting: `npm run lint`

A story fails QAS if any command exits non-zero.
```

### Step 2 — Verify the overlay resolves

The orchestrator looks for the overlay under:

```
<ORCH_TARGET_REPO>/.agentic/overrides/agents/<role>.append.md
```

where `ORCH_TARGET_REPO` defaults to the repo root (`ORCH_SPAWN_CWD`). If you
run under self-hosting, set `ORCH_OVERRIDES_DIR` to point at the project's
`.agentic/overrides/agents/` directory explicitly.

Confirm the file is in place:

```bash
ls .agentic/overrides/agents/
# qas.append.md
```

### Step 3 — Spawn the seat and confirm

When the orchestrator spawns the QAS seat it logs to stderr:

```
spawn-claude: NOTICE agent-def overlay applied: .agentic/overrides/agents/qas.append.md
```

The seat's prompt is composed as:
**`_common-rules.md` body + role-def body + overlay body**
(`scripts/orchestrator-spawn-claude.sh`, `build_agents_json()`). Later text
refines earlier text — the overlay wins where it contradicts the def.

### Step 4 — Migrate without conflict

Run the migration driver against the project:

```bash
scripts/migrate-project.sh /path/to/your-project
```

The def (`qas.md`) stays byte-pure upstream; the driver classifies it **REPLACE**
and updates it. The overlay (`qas.append.md`) lives under `.agentic/overrides/`,
which is a `project_owned_exceptions` surface by definition
(`.agentic/upgrade/ownership.yaml`); the driver never touches it.
Both the updated def body and your overlay are present in the next spawn.

---

## Limits

These constraints are enforced by the spawn seam (ADR-A-0022 D2):

| Constraint | Detail |
| ---------- | ------ |
| **Append-only, body-only** | Appended after the role body. Cannot reorder or delete def content. |
| **No frontmatter** | Any YAML frontmatter in the overlay is stripped and ignored; a NOTICE goes to stderr. |
| **Cannot widen `tools`** | Overlay `tools:` lines are ignored. Use `ORCH_TOOLS` at the runner level. |
| **Cannot change `model` or `name`** | Same: only the role def supplies these fields. |
| **Orchestrator-spawned seats only** | Task-tool subagents bypass the seam; overlay not applied (ABS-174). |

If a customization cannot be expressed as an append — for example, you need to
replace a section or restrict the def's behavior — it is an upstream feature
request (`.agentic/templates/consumer-feedback-item.md`), not a fork or overlay.

---

## How It Works (internals)

`build_agents_json()` in `scripts/orchestrator-spawn-claude.sh` composes the
emitted `--agents` JSON from three body buckets:

1. **Commons** — `_common-rules.md` (ABS-174)
2. **Role def** — `.claude/agents/<role>.md` (supplies `name`, `description`,
   `tools`, `model`)
3. **Overlay** — `.agentic/overrides/agents/<role>.append.md` (body only)

When no overlay file exists the emitted JSON is byte-identical to the pre-ABS-258
seam (fail-open). The awk parser keys the `tools` / `model` / `name` extraction
off the role-def file index (`ridx`), so even if an overlay carries a
`tools:` line it is never merged into the seat's privilege grant.

The overlay directory is determined by `ORCH_OVERRIDES_DIR` (override) or
`ORCH_TARGET_REPO` → `ORCH_SPAWN_CWD` → seam repo root (default). Under a plain
consumer project the harness and target are the same repo, so this is invisible.

---

## Related docs

- [BOILERPLATE_MIGRATION_SOP.md §3.3](../sop/BOILERPLATE_MIGRATION_SOP.md) —
  migration-context reference; decision table (overlay vs. `project_owned_exceptions`)
- [CONSUMER_FORK_DECLARATION_GUIDE.md](CONSUMER_FORK_DECLARATION_GUIDE.md) —
  the wholesale-fork path (`project_owned_exceptions`) for when you truly want to
  freeze your own def
- [ADR-A-0022](../../adrs/agentic/ADR-A-0022-agent-def-overlays.md) —
  the architectural decision record (append-only, body-only, spawn-seam
  materialization, no-tools-additive)
- [AGENT_CONFIGURATION_SOP.md](../sop/AGENT_CONFIGURATION_SOP.md) — general
  agent frontmatter format
