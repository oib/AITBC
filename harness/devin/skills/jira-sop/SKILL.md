---
name: jira-sop
description: "Jira ticket management via the Atlassian MCP server. Use to create a\
  \ Jira issue, comment on or attach evidence to a Jira issue, transition a Jira issue,\
  \ or search and read Jira issues; also migrating local mock tickets from work/tickets/\
  \ to Jira. Opens with a copy-paste Quick Reference for the five high-frequency ops\
  \ (dedup-search, create, comment, transition, read) with project key and cloudId\
  \ pre-filled \u2014 no schema-reading needed. Covers OAuth setup, cloudId resolution,\
  \ dedup, and createJiraIssue patterns. LEGACY SCOPE \u2014 Jira profile only (jira-github-postgres\
  \ or a custom Jira binding); not used with the agentic-backend profile."
triggers:
- user
- model
allowed-tools:
- exec
- grep
- read
---

# Jira SOP Skill (Atlassian MCP)

> **Scope: Jira-profile only.** This skill applies when the active profile binds
> `task-tracking` to `jira-cloud` (e.g. `profiles/jira-github-postgres/profile.yaml`).
> With the **agentic-backend** profile (ADR-A-0021), both the orchestrator and interactive
> sessions use `scripts/backend-tracker.sh` behind `$TRACKER_CMD` — no Atlassian MCP
> server and no `jira-sop` skill. Use the `tracker-ops` skill instead, which covers all
> three adapters (backend / Jira curl / mock) through the same CLI surface.
> See `profiles/neutral/adapters/task-tracking.md` (§ "Lane doctrine") for the full picture.

## Quick Reference — Five High-Frequency Ops

Copy-paste blocks for the day-to-day Jira ops. The project key and cached cloudId are
pre-filled from the active profile (`profiles/jira-github-postgres/profile.yaml`:
`project_key` / `jira_cloud_id`), so **no schema-reading is required for these five ops** —
paste, adjust the free-text values, and call. For anything beyond them (custom fields,
new issue types, unusual transitions) fall back to the full workflow below and read the
tool descriptors first.

> Replace `<atlassian-server>` with the connected server id (usually `user-atlassian`).
> `{{JIRA_CLOUD_ID}}` (cached cloudId) and `AITBC` (project key) resolve from
> the profile — the `{{JIRA_CLOUD_ID}}` token follows the same convention as `{{JIRA_SITE}}`.

### 1. Dedup-search (run before every create)

```text
CallMcpTool(
  server: "<atlassian-server>",
  toolName: "searchJiraIssuesUsingJql",
  arguments: {
    cloudId: "{{JIRA_CLOUD_ID}}",
    jql: 'project = AITBC AND (summary ~ "keyword" OR text ~ "keyword") ORDER BY created DESC',
    fields: ["summary", "status", "key"],
    maxResults: 20
  }
)
```

### 2. Create issue

```text
CallMcpTool(
  server: "<atlassian-server>",
  toolName: "createJiraIssue",
  arguments: {
    cloudId: "{{JIRA_CLOUD_ID}}",
    projectKey: "AITBC",
    issueTypeName: "Story",
    summary: "Concise action-oriented title",
    description: "<markdown body>",
    contentFormat: "markdown"
  }
)
```

### 3. Comment / attach evidence

```text
CallMcpTool(
  server: "<atlassian-server>",
  toolName: "addCommentToJiraIssue",
  arguments: {
    cloudId: "{{JIRA_CLOUD_ID}}",
    issueIdOrKey: "AITBC-123",
    commentBody: "**Dev Evidence**\n\n…"
  }
)
```

### 4. Transition

```text
# 1) list transitions to get the target id (project-specific)
CallMcpTool(
  server: "<atlassian-server>",
  toolName: "getTransitionsForJiraIssue",
  arguments: { cloudId: "{{JIRA_CLOUD_ID}}", issueIdOrKey: "AITBC-123" }
)
# 2) apply it
CallMcpTool(
  server: "<atlassian-server>",
  toolName: "transitionJiraIssue",
  arguments: {
    cloudId: "{{JIRA_CLOUD_ID}}",
    issueIdOrKey: "AITBC-123",
    transition: { id: "<id-from-step-1>" }
  }
)
```

### 5. Read

```text
CallMcpTool(
  server: "<atlassian-server>",
  toolName: "getJiraIssue",
  arguments: { cloudId: "{{JIRA_CLOUD_ID}}", issueIdOrKey: "AITBC-123" }
)
```

## Purpose

Guide consistent Jira ticket management through the **Atlassian MCP** server shipped in
`.cursor/mcp.json` (the `confluence-mcp` entry — Jira and Confluence share the
same Atlassian server and auth). Mirrors the canonical task-tracking contract in
`profiles/neutral/adapters/task-tracking.md` and reuses the evidence policy from
`linear-sop`.

> **Which Jira lane is this?** This skill is the **interactive lane** — a human-in-the-loop
> Cursor/Claude session driving Jira through the Atlassian MCP server. The **autonomous**
> orchestrator poll loop uses the other sanctioned lane (the `$TRACKER_CMD` curl adapter), and
> **neither replaces the other**. See the authoritative lane doctrine in
> `profiles/neutral/adapters/task-tracking.md` (§ "Lane doctrine: Jira MCP vs. `$TRACKER_CMD`
> curl adapter") for why each lane exists.

## When This Skill Applies

Invoke when:

- Creating, searching, commenting on, or transitioning Jira issues
- Migrating a local mock ticket (`work/tickets/<ID>.md`) to Jira
- Attaching dev/staging/done evidence to a Jira issue
- The active profile binds `task-tracking` to `jira-cloud` (see
  `profiles/jira-github-postgres/profile.yaml`)

## MCP Setup (one-time)

1. **Project config** — the shipped `.cursor/mcp.json` declares the Atlassian server
   under the `confluence-mcp` key (Jira reuses the Confluence/Atlassian
   server and its auth — there is no separate Jira entry). This is the verbatim shipped
   block:

```json
{
  "mcpServers": {
    "confluence-mcp": {
      "command": "npx",
      "args": ["-y", "@anthropic/confluence-mcp-server"],
      "env": {
        "ATLASSIAN_API_TOKEN": "your-token",
        "ATLASSIAN_EMAIL": "your-email",
        "CONFLUENCE_BASE_URL": "your-base-url"
      }
    }
  }
}
```

2. **Credentials** — the `env` values (`ATLASSIAN_API_TOKEN`, `ATLASSIAN_EMAIL`,
   `CONFLUENCE_BASE_URL`) are supplied at bootstrap (ABS-27). Providing real credentials
   is a human-only step (ADR-A-0004); do not authenticate the MCP or inject tokens
   yourself.

3. **Server name at runtime** — `CallMcpTool` targets the bootstrapped value of the
   `confluence-mcp` key from `.cursor/mcp.json`. Do **not** reference server
   ids that are absent post-bootstrap (e.g. a bare `atlassian`, `user-atlassian`, or
   `project-0-<workspace>-atlassian`). If a call fails with "server does not exist",
   confirm the key name in `.cursor/mcp.json` and that the server process started.

4. **Read tool schemas first (only beyond the five quick-ref ops)** — The five
   high-frequency ops in the Quick Reference above are pre-filled and need no schema
   read. For any other call, read the tool descriptor JSON under `mcps/<server>/tools/`
   before calling `CallMcpTool`.

## Core Tools

| Tool | Purpose |
|------|---------|
| `getAccessibleAtlassianResources` | Resolve `cloudId` (UUID) **once per session**; cache and reuse |
| `getVisibleJiraProjects` | List projects (`action: "create"`) |
| `getJiraProjectIssueTypesMetadata` | Epic / Story / Task / Bug availability |
| `getJiraIssueTypeMetaWithFields` | Required custom fields when create fails |
| `searchJiraIssuesUsingJql` | Dedup and backlog queries |
| `createJiraIssue` | Create epic, story, task, or bug |
| `getJiraIssue` | Read full issue |
| `addCommentToJiraIssue` | Post evidence or gate results |
| `transitionJiraIssue` | Move through workflow |
| `editJiraIssue` | Update fields after creation |

Confluence tools (`getConfluencePage`, `createConfluencePage`, …) share the same
`cloudId` and server if you publish to Confluence directly via MCP. The
`confluence-docs` skill is separate — it only generates local Markdown under `docs/`.

## cloudId Convention: Resolve Once, Reuse

Resolve `cloudId` a **single time per session** and reuse it for every Jira/Confluence
call:

1. Call `getAccessibleAtlassianResources` once (see Step 1 below).
2. Record the resolved UUID in a session scratch note (e.g. an in-context note or a
   `work/.cache/cloudId` scratch file).
3. Pass that cached UUID as `cloudId` on every subsequent call.

Do **not** re-call `getAccessibleAtlassianResources` per operation — it is a one-time
resolution step, never a per-op call.

## Standard Workflow: Create Ticket

**Mandatory:** run `duplicate-detection` before any create. No ticket without a dedup
verdict.

```text
Task Progress:
- [ ] Step 1: Resolve cloudId (once per session; reuse the cached value thereafter)
- [ ] Step 2: Dedup search (JQL)
- [ ] Step 3: Confirm project + issue type
- [ ] Step 4: createJiraIssue
- [ ] Step 5: Verify + clean up local mock file (if migrating)
```

### Step 1: Resolve cloudId (once per session)

```text
CallMcpTool(
  server: "confluence-mcp",
  toolName: "getAccessibleAtlassianResources",
  arguments: {}
)
```

Use the `id` field from the entry that includes `write:jira-work` scope. Pass that UUID
as `cloudId` on every subsequent call. Site URL (e.g. `your-site.atlassian.net`) also
works when the UUID is unknown. Cache the value (see the cloudId convention above) — do
not resolve it again for the rest of the session.

### Step 2: Dedup search

```text
CallMcpTool(
  server: "confluence-mcp",
  toolName: "searchJiraIssuesUsingJql",
  arguments: {
    cloudId: "<cloudId>",
    jql: 'project = AITBC AND (summary ~ "keyword" OR text ~ "keyword") ORDER BY created DESC',
    fields: ["summary", "status", "key"],
    maxResults: 20
  }
)
```

Apply `duplicate-detection` verdict: **reject** / **append** / **create**. On
**append**, use `addCommentToJiraIssue` instead of `createJiraIssue`.

### Step 3: Project and issue type

```text
CallMcpTool(
  server: "confluence-mcp",
  toolName: "getJiraProjectIssueTypesMetadata",
  arguments: {
    cloudId: "<cloudId>",
    projectIdOrKey: "AITBC"
  }
)
```

| Content | Issue type |
|---------|------------|
| User-facing feature ("As a … I want …") | **Story** |
| Technical / infra work | **Task** |
| Defect or regression | **Bug** |
| Large initiative with child stories | **Epic** |

### Step 4: Create issue

```text
CallMcpTool(
  server: "confluence-mcp",
  toolName: "createJiraIssue",
  arguments: {
    cloudId: "<cloudId>",
    projectKey: "AITBC",
    issueTypeName: "Story",
    summary: "Concise action-oriented title",
    description: "<markdown body — see template below>",
    contentFormat: "markdown"
  }
)
```

**Description template** (agent-ready ticket from `issue-enrichment`):

```markdown
## Goal
[Observable end state]

## Scope
**In scope:** …
**Out of scope:** …

## Acceptance Criteria
- [ ] …

## Definition of Done
- [ ] …

## Test Plan
- …

## ADR Context
- …

## Guardrail Annotation
- **Feasibility**: pass | flagged
- …
```

**Epic with children:** create the Epic first, capture `key` from the response, then
pass `parent: "<EPIC-KEY>"` on child `createJiraIssue` calls.

**Custom required fields:** if create fails, call `getJiraIssueTypeMetaWithFields` and
retry with `additional_fields` (e.g. `{"priority": {"name": "Medium"}}`).

### Step 5: Migrate from mock adapter

When filing a ticket that lived in `work/tickets/<ID>.md`:

1. Create in Jira (steps above); note the **assigned Jira key** (may differ from the
   local id — e.g. local `ABS-1` → Jira `ABS-25`).
2. Add a comment or description note: `Migrated from local mock ticket work/tickets/<ID>.md`.
3. **Delete** `work/tickets/<ID>.md` only after `createJiraIssue` succeeds.
4. Do **not** delete demo/reference tickets (e.g. `DEMO-1.md`) unless explicitly asked.

## Reading and Updating Issues

```text
# Read
CallMcpTool(server, "getJiraIssue", { cloudId, issueIdOrKey: "AITBC-25" })

# Comment (evidence)
CallMcpTool(server, "addCommentToJiraIssue", {
  cloudId,
  issueIdOrKey: "AITBC-25",
  commentBody: "**Dev Evidence**\n\n…"
})

# Transition
CallMcpTool(server, "getTransitionsForJiraIssue", { cloudId, issueIdOrKey })
CallMcpTool(server, "transitionJiraIssue", { cloudId, issueIdOrKey, transition: { id: "…" } })
```

(Reuse the cached `cloudId` from Step 1 — no re-resolution.)

## Evidence Policy (MUST)

Same phases as `linear-sop` — every issue needs evidence at each gate:

| Phase | Required? | Post via |
|-------|-----------|----------|
| **Dev** | MUST | `addCommentToJiraIssue` |
| **Staging** | MUST | `addCommentToJiraIssue` |
| **Done** | MUST | `addCommentToJiraIssue` |

Reuse the dev/staging/done templates from `harness/devin/skills/linear-sop/SKILL.md`; only
the transport changes (Jira comment instead of Linear comment).

## Status Workflow

Canonical statuses live in `profiles/neutral/adapters/statuses.yaml`. Map provider
states via the jira-cloud adapter binding. Typical Jira Software mapping:

```text
Backlog → Ready → In Progress → Testing → Ready for Review → Done
```

Use `transitionJiraIssue` after `getTransitionsForJiraIssue` — transition ids are
project-specific.

## JQL Quick Reference

```text
# Open issues in project
project = AITBC AND status != Done ORDER BY updated DESC

# Recent stories
project = AITBC AND issuetype = Story ORDER BY created DESC

# Text search (dedup)
project = AITBC AND text ~ "evolver self-evolution" ORDER BY created DESC
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `MCP server does not exist` | Use the `confluence-mcp` key from `.cursor/mcp.json`; confirm the server started and its `env` credentials are set |
| `createJiraIssue` 400 / required field | `getJiraIssueTypeMetaWithFields` → `additional_fields` |
| Local id ≠ Jira key | Expected — Jira auto-increments; use returned `key` |
| Confluence MCP errored separately | Jira and Confluence share the Atlassian server and auth; re-check `env` credentials |

## Authoritative References

- **Task-tracking contract:** `profiles/neutral/adapters/task-tracking.md`
- **Lane doctrine (MCP interactive lane vs. `$TRACKER_CMD` curl autonomous lane):**
  `profiles/neutral/adapters/task-tracking.md` (§ "Lane doctrine: Jira MCP vs. `$TRACKER_CMD` curl adapter")
- **Jira profile example:** `profiles/jira-github-postgres/profile.yaml`
- **Dedup gate:** `harness/devin/skills/duplicate-detection/SKILL.md`
- **Ticket formatting:** `harness/devin/skills/issue-enrichment/SKILL.md`
- **Evidence templates:** `harness/devin/skills/linear-sop/SKILL.md`
- **MCP config:** `.cursor/mcp.json`, `.cursor/rules/31-mcp-integration.mdc`
