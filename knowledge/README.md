# Project Knowledge Base (OKF bundle)

Pre-summarized knowledge about this project in the
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf):
one markdown file per concept, YAML frontmatter for queryable fields, `index.md` for
progressive disclosure, cross-links between concepts.

Agents consult [`index.md`](index.md) **before** any broad repository exploration — see the
mandatory context sequence in
[`profiles/neutral/adapters/knowledge.md`](../profiles/neutral/adapters/knowledge.md) and
[ADR-A-0003](../adrs/agentic/ADR-A-0003-context-minimization.md).

## Concept file template

```markdown
---
type: concept            # concept | capability | module | domain-term
resource: <what this documents, e.g. a module path or capability name>
tags: [architecture]
timestamp: YYYY-MM-DD
---

# <Concept name>

One-paragraph summary an agent can act on without opening source files.

## Rules and constraints

- …

## Related

- [[other-concept]] — why it's related
- Source: `path/to/module/` (open only when the task names it)
```

## Code graph (graphify)

A [graphify](https://github.com/safishamsi/graphify) knowledge graph of the whole repo lives in
`graphify-out/` (`graph.json` + `GRAPH_REPORT.md`). It complements this bundle at levels 2–4 of
the context sequence: query it (`graphify explain "X"`, `graphify path "A" "B"`) before any
broad grep. Refresh with `graphify update .` after code changes — AST-based, no API cost.

## Maintenance

- Keep `index.md` current: one line per concept (name + hook). It is the level-1 context load.
- The documentation workflow (`/update-docs`) refreshes concept files affected by merged scope,
  in the same PR when possible.
- A stale or wrong concept file is a defect — file a ticket against it like any other bug.
