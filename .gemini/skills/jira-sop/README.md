# Jira SOP (Atlassian MCP)

![Status](https://img.shields.io/badge/status-production-green)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)
![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> Jira ticket management via the Atlassian MCP server — create, search, comment, transition, and migrate mock tickets.

## Quick Start

Activates when you:

- Create or update Jira issues through Atlassian MCP
- Migrate `work/tickets/*.md` mock files to Jira
- Attach dev/staging/done evidence as Jira comments
- Run the mandatory dedup gate against Jira (JQL)

## Trigger Keywords

| Primary | Secondary |
|---------|-----------|
| Jira | Atlassian MCP |
| createJiraIssue | cloudId |
| JQL | migrate mock ticket |
| ABS | evidence |

## Related Skills

- [duplicate-detection](../duplicate-detection/) — mandatory pre-create gate
- [issue-enrichment](../issue-enrichment/) — agent-ready ticket body
- [linear-sop](../linear-sop/) — evidence templates (same policy, Linear transport)
- [confluence-docs](../confluence-docs/) — local Markdown docs templates (docs/), not MCP publishing

---

*Full implementation details in [SKILL.md](SKILL.md)*
