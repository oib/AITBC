---
id: ADR-A-0010
title: Minimal-change discipline (Ponytail) is the default for coding and review agents
status: proposed
scope: agentic
date: "2026-07-02"
---

## Context

Agents over-produce by default: speculative abstractions, drive-by refactors, dependency
sprawl. In a multi-agent system this compounds — every unnecessary line is context someone else
must load, review, and maintain.

## Decision

We will make the Ponytail / minimal-change skill a mandatory default for all coding and review
agents. The skill ships in-repo at `harness/claude/skills/ponytail/`, mirrored to the
provider-neutral source `.agents/skills/ponytail/` and to `.gemini/skills/ponytail/`, and its
discipline is also stated inline in each coding/review
agent definition — so the mandate resolves in every consuming project, not only where a
private user-level skill happens to exist. The discipline: prefer minimal, scoped, reversible changes; standard
library and platform features before dependencies; no unnecessary abstractions, rewrites, or
broad refactors inside feature tickets. Genuine refactor needs become findings routed through
the review-followup chain into their own prioritized tickets. Review agents flag
over-engineering as findings, same as bugs.

## Consequences

Diffs stay reviewable by humans at merge time. Refactors happen deliberately, with PO
prioritization, instead of ambiently. Where minimal genuinely conflicts with an accepted ADR or
acceptance criterion, the ADR/AC wins and the tension is recorded in the handoff record.
