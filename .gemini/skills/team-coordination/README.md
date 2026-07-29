# Team Coordination

![Status](https://img.shields.io/badge/status-beta-yellow)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)
![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> Agent Teams orchestration patterns for multi-agent SAFe workflows. Use when spawning agent teams, coordinating teammates, enforcing quality gates, or orchestrating the 17-agent SAFe pipeline.

## Quick Start

This skill is invoked manually with `/team-coordination`:

```
/team-coordination Implement AITBC-XXX user profile feature
```

## What This Skill Does

Provides patterns for Claude Code Agent Teams -- real-time multi-agent coordination with shared TaskList, inter-agent messaging, and SAFe quality gate enforcement via task dependencies.

## Trigger Keywords

| Primary | Secondary |
|---------|-----------|
| agent team | spawn teammates |
| team coordination | parallel agents |
| multi-agent | SAFe pipeline |
| TeamCreate | quality gates |

## Prerequisites

Agent Teams must be enabled (experimental):

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

## Related Skills

- [agent-coordination](../agent-coordination/) - Agent assignment without teams
- [orchestration-patterns](../orchestration-patterns/) - Single-agent orchestration

## Maintenance

| Field | Value |
|-------|-------|
| Last Updated | 2026-03-05 |
| Harness Version | v2.35.0 |

---

*Full implementation details in [SKILL.md](SKILL.md)*
