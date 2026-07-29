# Stop Slop

![Status](https://img.shields.io/badge/status-production-green)
![Harness](https://img.shields.io/badge/harness-v2.35.0-blue)
![Provider](https://img.shields.io/badge/provider-Gemini_CLI-orange)

> Output-quality gate against AI "slop": filler, AI tells, unverified claims, invented APIs, and unrequested scope.

## Provenance

**Vendored from:** [github.com/hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop)
**Upstream author:** Hardik Pandya ([hvpandya.com](https://hvpandya.com))
**License:** MIT (see [LICENSE](LICENSE) in this directory — upstream copyright retained)

## Purpose

Run this skill before returning any substantial deliverable — a spec, PR description, doc, review
summary, or multi-paragraph answer — to strip filler and AI tells, verify every named identifier
against the repo, and cut unrequested scope. Score the draft on five dimensions (Directness,
Rhythm, Trust, Authenticity, Density); below 35/50, revise before handoff.
