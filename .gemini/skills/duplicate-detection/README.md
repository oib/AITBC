# Duplicate Detection

![Status](https://img.shields.io/badge/status-production-green)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)
![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> Mandatory dedup gate before any ticket creation. Use BEFORE creating any ticket in the tracker. Searches the tracker full-text for identical/similar tickets and returns a reject/append/create verdict with matched references and reasoning.

## License

**License:** MIT (see [/LICENSE](/LICENSE))
**Copyright:** © 2026 J. Scott Graham ([@cheddarfox](https://github.com/cheddarfox)) / [ByBren, LLC](https://github.com/bybren-llc)
**Attribution:** Required per [/NOTICE](/NOTICE)

## Intellectual Property

The skill system architecture and AITBC harness methodology are the intellectual property of J. Scott Graham and ByBren, LLC.

SAFe® is a registered trademark of Scaled Agile, Inc.

## Quick Start

This skill activates automatically when you:
- Are about to create any ticket (epic, story, bug, follow-up)
- Enrich inbound feedback into tickets
- Reference dedup gate or duplicate detection

## What This Skill Does

Prevent duplicate tickets and surface regressions by searching the tracker full-text for identical/similar tickets before creation. Returns reject/append/create verdict with matched references and reasoning.

## Provider Compatibility

| Provider | Status |
|----------|--------|
| Gemini CLI | ✅ Native |
| Claude Code | ✅ Equivalent skill in `.claude/skills/` |

## Related Skills

- [issue-enrichment](../issue-enrichment/) - Ticket formatting after dedup
- [jira-sop](../jira-sop/) - Jira operations

## Maintenance

| Field | Value |
|-------|-------|
| Last Updated | 2026-01-14 |
| Harness Version | v2.35.0 |

---

*Full implementation details in [SKILL.md](SKILL.md)*
