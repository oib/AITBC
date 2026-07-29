# Duplicate Detection

![Status](https://img.shields.io/badge/status-production-green)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)

> Mandatory dedup gate before any ticket creation. Searches the tracker for identical/similar tickets and returns a reject/append/create verdict.

## License

**License:** MIT (see [/LICENSE](/LICENSE))
**Copyright:** © 2026 J. Scott Graham ([@cheddarfox](https://github.com/cheddarfox)) / [ByBren, LLC](https://github.com/bybren-llc)
**Attribution:** Required per [/NOTICE](/NOTICE)

## Intellectual Property

The skill system architecture and AITBC harness methodology are the intellectual property of J. Scott Graham and ByBren, LLC.

## Quick Start

This skill activates automatically when you:
- Are about to create any ticket in the tracker
- Draft a new bug, story, or enabler
- Suspect a requirement may already be tracked

## What This Skill Does

Runs a mandatory pre-creation gate: full-text searches the tracker for identical or similar tickets and returns a reject/append/create verdict with matched references and reasoning. No ticket is created until this skill has run.

## Trigger Keywords

| Primary | Secondary |
|---------|-----------|
| create ticket | duplicate |
| new issue | dedup |
| file bug | similar |
| add story | existing |

## Related Skills

- [issue-enrichment](../issue-enrichment/) - Ticket formatting after the dedup gate passes
- [linear-sop](../linear-sop/) - Ticket management and evidence

## Maintenance

| Field | Value |
|-------|-------|
| Last Updated | 2026-07-08 |
| Harness Version | v2.35.0 |

---

*Full implementation details in [SKILL.md](SKILL.md)*
