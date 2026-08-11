# Agent Configuration SOP

## Standard Operating Procedure for Configuring Claude Code Agents

**Version**: 1.0
**Last Updated**: 2025-10-03
**Owner**: AITBC Development Team

---

## Overview

This SOP defines how to configure and maintain the 17-agent system for the AITBC application.
All agent configurations use YAML frontmatter to specify tool restrictions and model selection.

## Agent Configuration Format

### YAML Frontmatter Structure

Every agent file in `.claude/agents/` must start with YAML frontmatter:

```yaml
---
name: agent-name
description: Brief description of agent role
tools: [Tool1, Tool2, Tool3]
model: opus|sonnet
---
```

### Required Fields

| Field         | Description                          | Example                                  |
| ------------- | ------------------------------------ | ---------------------------------------- |
| `name`        | Unique agent identifier (kebab-case) | `be-developer`                           |
| `description` | Brief role description               | `Backend Developer - API implementation` |
| `tools`       | Array of allowed tools               | `[Read, Write, Edit, Bash]`              |
| `model`       | AI model selection                   | `opus` or `sonnet`                       |

---

## Tool Restrictions by Agent Role

### Planning Agents (Opus Model)

### BSA (Business Systems Analyst)

```yaml
tools: [Read, Write, Edit, Bash, Grep, Glob, mcp__linear-mcp__*]
model: opus
```

- **Why**: Needs Linear access for ticket analysis and spec creation
- **Why Opus**: Complex planning and requirements decomposition

### System Architect

```yaml
tools: [Read, Write, Edit, Bash, Grep, Glob]
model: opus
```

- **Why**: Pattern validation and architectural decisions
- **Why Opus**: High-level architectural thinking required

### Execution Agents (Sonnet Model)

### BE Developer

```yaml
tools: [Read, Write, Edit, Bash, Grep, Glob]
model: sonnet
```

- **Why**: Implementation only, no Linear/git access (RTE handles)
- **Why Sonnet**: Fast, efficient implementation

### FE Developer

```yaml
tools: [Read, Write, Edit, Bash, Grep, Glob]
model: sonnet
```

- **Why**: UI implementation only
- **Why Sonnet**: Fast, efficient implementation

### Data Engineer

```yaml
tools: [Read, Write, Edit, Bash, Grep, Glob]
model: sonnet
```

- **Why**: Schema changes and migrations
- **Why Sonnet**: Structured implementation work

### Data Provisioning Engineer

```yaml
tools: [Read, Write, Edit, Bash, Grep, Glob]
model: sonnet
```

- **Why**: ETL and data pipeline implementation
- **Why Sonnet**: Structured implementation work

### Quality Agents (Sonnet Model)

### QAS (Quality Assurance Specialist) - Gate Owner (v1.4)

```yaml
tools:
  [
    Read,
    Bash,
    Grep,
    mcp__linear-mcp__create_comment,
    mcp__linear-mcp__update_issue,
    mcp__linear-mcp__list_comments,
  ]
model: sonnet
```

- **Why Read/Bash/Grep**: Test execution and validation (no code modification)
- **Why Linear MCP**: Posts final evidence + verdict to Linear (system of record)
- **Why Sonnet**: Efficient test validation
- **Role (v1.4)**: Gate Owner with iteration authority - work does not proceed without QAS approval

### Security Engineer

```yaml
tools: [Read, Bash, Grep]
model: sonnet
```

- **Why**: Security audits and validation only
- **Why Sonnet**: Focused security checks

### Documentation Agent (Sonnet Model)

### Tech Writer

```yaml
tools: [Read, Write, Edit, Grep, Glob, Bash]
model: sonnet
```

- **Why**: Documentation creation and editing, batch doc updates
- **Why Grep/Glob**: Find files needing updates across large doc sets
- **Why Sonnet**: Efficient documentation writing

### Coordination Agents (Sonnet Model)

### TDM (Technical Delivery Manager)

```yaml
tools: [Read, Bash, mcp__linear-mcp__*, mcp__confluence-mcp__*]
model: sonnet
```

- **Why**: Orchestration, Linear/Confluence updates, no code modification
- **Why Sonnet**: Efficient coordination and management

### RTE (Release Train Engineer) - PR Shepherd (v1.4)

```yaml
tools: [Read, Bash, Grep]
model: sonnet
```

- **Why Read/Bash/Grep**: Git/PR management via Bash (git commands, gh CLI)
- **Why Sonnet**: Efficient release coordination
- **Role (v1.4)**: PR Shepherd - creates PRs, monitors CI, but does NOT write product code or merge
- **Boundaries**: oib (HITL) remains final merge authority. RTE shepherds PRs to "Ready for HITL Review"

---

## Model Selection Criteria

### When to Use Opus

- **Complex Planning**: BSA requirements decomposition
- **Architectural Decisions**: System Architect pattern validation
- **Strategic Thinking**: High-level design and tradeoff analysis

**Cost**: Higher per token, but critical for planning accuracy

### When to Use Sonnet

- **Implementation**: All execution agents (BE, FE, DE, etc.)
- **Testing**: QAS and Security Engineer
- **Documentation**: Tech Writer
- **Coordination**: TDM and RTE

**Cost**: Lower per token, optimized for structured tasks

---

## Tool Access Guidelines

### Core Tools

**Available to Most Agents**:

- `Read` - Read files (all agents)
- `Write` - Create new files (implementation agents)
- `Edit` - Modify existing files (implementation agents)
- `Bash` - Execute bash commands (most agents)
- `Grep` - Search file contents (implementation and quality agents)
- `Glob` - File pattern matching (implementation agents)

### Restricted Tools

**Linear MCP** (`mcp__linear-mcp__*`):

- ✅ BSA - Ticket analysis and spec creation
- ✅ TDM - Orchestration and progress updates
- ✅ QAS (v1.4) - Evidence posting and verdict (Gate Owner role - system of record)
- ❌ Execution agents - No direct Linear access (reduces noise)

**Confluence MCP** (`mcp__confluence-mcp__*`):

- ✅ TDM - Documentation coordination
- ❌ Others - Limited to essential use cases

### Git Operations

**Via Bash Tool**:

- ✅ RTE - PR creation, branch management (via `git` and `gh` commands)
- ❌ Execution agents - No direct git access (RTE handles releases)

---

## Adding a New Agent

### Step 1: Create Agent File

```bash
# Create file in .claude/agents/
touch .claude/agents/new-agent.md
```

### Step 2: Add Frontmatter

```yaml
---
name: new-agent
description: Brief role description
tools: [appropriate tools based on role]
model: opus|sonnet
---
# Agent Name

## Role Overview

[Description of agent responsibilities]
```

### Step 3: Determine Tool Access

**Ask**:

1. Does this agent need to create/modify code? → `Write`, `Edit`
2. Does this agent need to run tests/validation? → `Bash`
3. Does this agent need to update Linear? → `mcp__linear-mcp__*`
4. Does this agent need to search codebase? → `Grep`, `Glob`

### Step 4: Select Model

**Opus if**:

- Complex planning or architecture
- Strategic decision-making
- Pattern creation/validation

**Sonnet if**:

- Implementation work
- Testing and validation
- Documentation
- Coordination

### Step 5: Test Configuration

```bash
# Verify frontmatter syntax
head -10 .claude/agents/new-agent.md

# Test agent invocation (after restart)
# Main Claude uses Task tool to invoke agent
```

---

## Harness Source of Truth

`harness/claude/agents/` is the **authoritative source** for all agent definitions.
The live `.claude/agents/` directory is a generated output (`generated(pin v2.22.0)`)
and must **never** be hand-edited — the drift guard (`tests/tooling/test-harness-parity.sh`) fails
if it diverges from the harness. `agent_providers/claude_code/prompts/` is a second
generated mirror.

### Edit Workflow

```bash
# 1. Edit the harness source — NOT the live .claude/ copy
#    harness/claude/agents/<role>.md

# 2. Regenerate the provider mirror
bash scripts/generate-governor.sh --providers

# 3. Verify parity (must stay green — all 6 tests)
bash tests/tooling/test-harness-parity.sh

# 4. Commit both the harness edit and the regenerated mirror together
git add harness/claude/agents/<role>.md \
        agent_providers/claude_code/prompts/<role>.md
git commit -m "feat(harness): <description> [TICKET-XXX]"
```

The live `.claude/agents/<role>.md` updates automatically at the next boilerplate
promotion — do not touch it manually.

---

## Agent Definition Size Management

Opus-model agents (System Architect, BSA) load their full system prompt on every spawn.
A 37 KB agent definition costs ~9,200 tokens at each invocation — before any work begins.
Keep agent definitions under **~12–15 KB**. Definitions that grow beyond this threshold
should apply the slim + reference pattern.

### Prompt Size Budget (commons + role + overlay) — sensor-enforced

The number that actually reaches the model is not the role def alone: the spawn seam
(`scripts/orchestrator-spawn-claude.sh`) **composes** `_common-rules.md` (ABS-174, ~13.8 KB) +
the role def + any project overlay (ADR-A-0022) into one prompt loaded on **every turn**. That
composed payload is the single largest controllable cost item in a run (22–60 % of paid input;
see `work/improvement-proposals/2026-07-25-token-efficiency-prefix-amplification.md`).

**Declared budget: a seat's composed prompt (`_common-rules.md` + `<role>.md` + `<role>.append.md`)
must stay ≤ 24000 bytes.** A role over budget is a **DEFECT**, not an operating mode.

The budget is measured and enforced mechanically by **`scripts/agent-prompt-size.sh`**:

```bash
scripts/agent-prompt-size.sh            # report every seat's IST size, largest first
scripts/agent-prompt-size.sh --check    # gate: exit 1 if any seat exceeds the budget
scripts/agent-prompt-size.sh --budget 30000   # measure against a different budget
```

`tests/tooling/test-agent-prompt-size-budget.sh` runs the sensor in CI: it proves the measurement is
correct and holds a **ratchet** — the count of over-budget roles must never rise above today's
known-debt ceiling, so any *new* bloat (a newly over-budget role, or a heavier `_common-rules.md`)
turns the suite red. Reducing the existing over-budget roles below the budget is the follow-up
shortening work (ABS-566 remainder); as roles drop under budget, lower the ratchet in that test.

Budget overridable via `ORCH_PROMPT_SIZE_BUDGET`; agents dir via `ORCH_AGENTS_DIR`.

### Slim + Reference Pattern

Keep decision rules, gate criteria, handoff contracts, output formats, and escalation
triggers in the prompt — they are needed on every turn. Move examples, long templates,
evidence patterns, search commands, and background rationale to an on-demand reference
file that is only loaded when that specific artifact is being produced.

**Structure:**

```
harness/claude/agents/<role>.md      ← in-prompt: decision rules + triggers (~12–15 KB)
docs/sop/<role>-reference.md          ← on-demand: verbose supporting material
```

**In-prompt trigger phrase** (add near the top of the agent def body):

```markdown
Verbose supporting material — search-command examples, long templates, evidence patterns,
and background rationale — lives in **`docs/sop/<role>-reference.md`**; read it only in
the turn that produces that artifact.
```

Then replace each moved section with a one-line pointer: `"… : reference §N"`.

**What stays in-prompt:** gate criteria, handoff contracts, exit protocols, escalation
triggers, non-negotiables, output-format specs.

**What moves to the reference doc:** search command examples, long verdict/ADR/PR-review
templates, code patterns, background rationale.

### Applying the Pattern

1. Audit the agent def — mark each section as "decision rule" or "reference material".
2. Move reference material to `docs/sop/<role>-reference.md` with numbered sections (§1, §2, …).
3. Add the in-prompt trigger phrase.
4. Replace each moved section with a `"… : reference §N"` pointer.
5. Consolidate scattered MANDATORY paragraphs into a single **Non-negotiables** list.
6. Verify size: `wc -c harness/claude/agents/<role>.md` (target ≤ 15 KB).
7. Follow the **Harness Source of Truth** edit workflow above.

**Reference implementation:** `harness/claude/agents/system-architect.md` (slimmed
37.9 KB → 14.8 KB, ABS-170) and `docs/sop/system-architect-reference.md`.

---

## Modifying Existing Agents

**Always edit `harness/claude/agents/`** (see [Harness Source of Truth](#harness-source-of-truth) above).

### Changing Tool Access

1. Read current agent file in `harness/claude/agents/`
2. Update `tools` array in frontmatter
3. Document reason for change in git commit
4. Update this SOP if pattern changes

**Example**:

```bash
# Before
tools: [Read, Bash]

# After (adding grep capability)
tools: [Read, Bash, Grep]
```

### Changing Model Selection

1. Evaluate if agent role changed (planning vs execution)
2. Update `model` field
3. Test performance and cost impact
4. Document in Linear ticket

---

## Validation Checklist

Before committing agent configuration changes:

- [ ] YAML frontmatter syntax is valid
- [ ] `name` field matches filename (kebab-case)
- [ ] `tools` array includes only necessary tools
- [ ] `model` selection appropriate for agent role
- [ ] Agent description is clear and concise
- [ ] Tool restrictions documented in this SOP
- [ ] Changes tested with agent invocation

---

## Troubleshooting

### Agent Cannot Access Tool

**Error**: "Tool X not available to agent Y"

**Solution**:

1. Check agent frontmatter `tools` array
2. Add required tool if justified by agent role
3. Update SOP with rationale

### Agent Using Wrong Model

**Error**: Performance issues or unexpected behavior

**Solution**:

1. Verify `model` field in frontmatter
2. Confirm Opus for planning, Sonnet for execution
3. Test with corrected model

### Frontmatter Parse Error

**Error**: Agent fails to load

**Solution**:

1. Verify YAML syntax (proper indentation, quotes)
2. Ensure `---` delimiters on separate lines
3. Validate with YAML linter if needed

---

## Related Documentation

- [Agent Workflow SOP](./AGENT_WORKFLOW_SOP.md) - How to invoke and orchestrate agents
- [AGENTS.md](/AGENTS.md) - Agent team quick reference
- [CONTRIBUTING.md](/CONTRIBUTING.md) - Development workflow
- [system-architect-reference.md](./system-architect-reference.md) - Reference implementation of the slim + reference pattern (ABS-170)

---

**Questions?** Contact AITBC Development Team or System Architect
