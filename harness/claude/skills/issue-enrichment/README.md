# Issue Enrichment

![Status](https://img.shields.io/badge/status-production-green)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)

> Agent-ready ticket formatting and guardrail annotation before ticket creation. Use AFTER the duplicate-detection gate returns an append/create verdict.

## License

**License:** MIT (see [/LICENSE](/LICENSE))
**Copyright:** © 2026 J. Scott Graham ([@cheddarfox](https://github.com/cheddarfox)) / [ByBren, LLC](https://github.com/bybren-llc)
**Attribution:** Required per [/NOTICE](/NOTICE)

## Intellectual Property

The skill system architecture and AITBC harness methodology are the intellectual property of J. Scott Graham and ByBren, LLC.

## Quick Start

This skill activates automatically when you:
- Have a drafted requirement that passed the dedup gate
- Need to format a ticket into goal/scope/acceptance-criteria/references
- Must annotate a ticket with its guardrails before creation

## What This Skill Does

Formats a drafted requirement into the agent-ready structure and runs the guardrail-feasibility checklist (ADR hierarchy, human-approval boundaries, minimal-change default), producing the guardrail annotation block written into the ticket body. It formats and annotates — it never adds requirements the draft does not contain.

## Trigger Keywords

| Primary | Secondary |
|---------|-----------|
| enrich ticket | format |
| acceptance criteria | guardrail |
| agent-ready | annotate |
| ticket scope | references |

## Related Skills

- [duplicate-detection](../duplicate-detection/) - Mandatory dedup gate run before enrichment
- [linear-sop](../linear-sop/) - Ticket management and evidence

## Maintenance

| Field | Value |
|-------|-------|
| Last Updated | 2026-07-08 |
| Harness Version | v2.35.0 |

---

*Full implementation details in [SKILL.md](SKILL.md)*
