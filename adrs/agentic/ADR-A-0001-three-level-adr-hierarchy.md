---
id: ADR-A-0001
title: Three-level ADR hierarchy with fixed authority order
status: proposed           # accepted by the adopting human at bootstrap (edit status + accepted_by)
scope: agentic
date: "2026-07-02"
---

## Context

Agentic projects need decisions at three distinct altitudes: organization-wide rules (GDPR,
company design system, engineering constraints), agentic-SDLC rules that apply across projects,
and project-local architecture. One flat ADR pile forces every project to re-litigate shared
decisions; no hierarchy at all makes conflicts unresolvable.

## Decision

We will keep three ADR levels — `adrs/company/`, `adrs/agentic/`, `adrs/project/` — with the
fixed authority order:

**Accepted project ADR > Accepted company ADR > Accepted agentic ADR > governance defaults.**

A narrower ADR may override a broader one only when explicitly accepted by a human and only
while naming the overridden ADR in its `overrides` field. Agentic ADRs are copied into projects
at bootstrap and updated through upgrades; company ADRs are referenced or added manually (not
copied by default in v1); project ADRs are local.

## Consequences

Conflicts resolve mechanically by authority order. Boilerplate upgrades can evolve agentic ADRs
without touching project decisions. Every override is auditable (named, human-accepted).
Adopting companies rarely need to customize agentic ADRs — that is the design intent.
