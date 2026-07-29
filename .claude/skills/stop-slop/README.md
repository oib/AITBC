# Stop Slop

![Status](https://img.shields.io/badge/status-production-green)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)

> Output-quality gate against AI "slop": filler, AI tells, unverified claims, invented APIs, and unrequested scope.

## Provenance

**Vendored from:** [github.com/hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop)
**Upstream author:** Hardik Pandya ([hvpandya.com](https://hvpandya.com))
**License:** MIT (see [LICENSE](LICENSE) in this directory — upstream copyright retained)

`SKILL.md` and `references/` are the upstream content. Only the frontmatter and a "Repo-Specific
Additions" section were adapted for this harness; the harness integration wiring is ByBren, LLC
work product.

## Quick Start

Invoke this skill before returning any substantial deliverable:

- A spec, planning doc, or acceptance criteria
- A PR description or commit message body
- Documentation, a README, or a runbook
- A review or QA validation summary
- Any multi-paragraph answer

It gives an explicit checklist (banned phrases, structural clichés, active voice, verified
identifiers, no unrequested scope) plus a five-dimension score. Below 35/50, revise before handoff.

## Integrated Seats

Wired into the deliverable-producing agent seats: `be-developer`, `fe-developer`, `data-engineer`,
`qas`, `system-architect`, `rte` (via the "Built-in skills for this seat" mapping) and `bsa`,
`tech-writer` (via a MANDATORY anti-slop gate section, since those seats lack the `Skill` tool).
