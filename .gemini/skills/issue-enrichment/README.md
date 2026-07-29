# Issue Enrichment

![Status](https://img.shields.io/badge/status-production-green)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)
![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> Agent-ready ticket formatting and guardrail annotation before ticket creation. Use AFTER the duplicate-detection gate returns an append/create verdict. Formats a drafted requirement into the goal/scope/acceptance-criteria/references structure, runs the guardrail-feasibility checklist (ADR hierarchy, human-approval boundaries, minimal-change default), and produces the guardrail annotation block written into the ticket body.

## License

**License:** MIT (see [/LICENSE](/LICENSE))
**Copyright:** © 2026 J. Scott Graham ([@cheddarfox](https://github.com/cheddarfox)) / [ByBren, LLC](https://github.com/bybren-llc)
**Attribution:** Required per [/NOTICE](/NOTICE)

## Intellectual Property

The skill system architecture and AITBC harness methodology are the intellectual property of J. Scott Graham and ByBren, LLC.

SAFe® is a registered trademark of Scaled Agile, Inc.

## Quick Start

This skill activates automatically when you:
- Format a drafted requirement into a ticket
- Add guardrail annotations before ticket creation
- Reference issue enrichment or ticket formatting

## What This Skill Does

Turn a drafted requirement into an agent-ready ticket with structured goal/scope/acceptance-criteria/references and guardrail annotations for feasibility constraints.

## Provider Compatibility

| Provider | Status |
|----------|--------|
| Gemini CLI | ✅ Native |
| Claude Code | ✅ Equivalent skill in `.claude/skills/` |

## Related Skills

- [duplicate-detection](../duplicate-detection/) - Dedup gate before enrichment
- [jira-sop](../jira-sop/) - Tracker operations

## Maintenance

| Field | Value |
|-------|-------|
| Last Updated | 2026-01-14 |
| Harness Version | v2.35.0 |

---

*Full implementation details in [SKILL.md](SKILL.md)*
