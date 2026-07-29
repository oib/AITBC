# Project ADRs

Project-specific architectural decisions — storage choices, API style, module boundaries,
anything the [capability map](../../profiles/README.md) alone can't govern. Local to this
project; never copied or upgraded.

- Template: the shared [ADR format](../agentic/README.md) with
  `scope: project`, ids `ADR-P-nnnn`.
- **Agents create project ADRs only in `proposed` status** (typically the Architect Agent,
  routed from epic decomposition or the adr-check gate). Humans accept.
- A project ADR may override a company or agentic ADR **only** with an explicit `overrides:`
  reference and human acceptance — it then wins by authority order
  ([ADR-A-0001](../agentic/ADR-A-0001-three-level-adr-hierarchy.md)).
- The Ticket Creation Agent embeds accepted-ADR excerpts into tickets (`adr_context`), so keep
  Decision sections short and quotable.
