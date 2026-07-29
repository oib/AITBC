# Tracker Ops (adapter CLI)

![Status](https://img.shields.io/badge/status-production-green)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)
![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> Copy-paste quick reference for the `$TRACKER_CMD` adapter CLI (jira-tracker.sh / mock-tracker.sh) — read, comment, transition, search, and link tickets without running `help`.

## Quick Start

Activates when you:

- Read a ticket's state (`get`) on a resumed or fresh spawn
- Post gate results / evidence / a decision comment (`comment --body-file`)
- Perform your exit transition (`transition --expect-from`)
- Search or link tickets from an autonomous seat

## Trigger Keywords

| Primary | Secondary |
|---------|-----------|
| ticket lesen | $TRACKER_CMD |
| kommentieren | jira-tracker.sh |
| transitionieren | mock-tracker.sh |
| get / comment / transition | --body-file / --expect-from |

## Related Skills

- [jira-sop](../jira-sop/) — interactive Atlassian MCP lane (this skill is the autonomous adapter lane)
- [run-boilerplate](../run-boilerplate/) — sandbox to smoke-test adapter calls
- [linear-sop](../linear-sop/) — evidence templates (same policy)

---

*Full implementation details in [SKILL.md](SKILL.md)*
