---
id: ADR-A-0011
title: Three-layer application architecture is the default
status: proposed
scope: agentic
date: "2026-07-02"
---

## Context

Projects built on the boilerplate need a shared default for structuring application code.
Without one, every project re-litigates layering, and frontends quietly grow direct database
access that no reviewer is mandated to catch. (This is distinct from the harness's
Hooks → Commands → Skills "three-layer architecture", which describes tooling, not
application code.)

## Decision

We will default every project built on the boilerplate to three application layers:

- **Data layer** — databases, filesystems, and other stores.
- **Business layer** — all business logic; the sole consumer of the data layer.
- **Frontend layer** — display only; reaches business logic via API, never the data layer
  directly.

The layers are roles, not technologies: for non-web projects the "API" may be an in-process
module boundary rather than a network service. This is a **default**, overridable only by an
accepted project-level ADR that names ADR-A-0011 as superseded for that project (authority
order, ADR-A-0001).

## Consequences

System Architect Stage-1 review checks layering (no frontend→data-layer access). Business
logic stays testable independent of any UI or storage choice. Projects with a genuine reason
to deviate record it once, human-accepted and auditable, instead of eroding the boundary
silently.
