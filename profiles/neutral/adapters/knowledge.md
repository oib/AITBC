# Knowledge Adapter — Interface

The project knowledge base: pre-summarized, queryable knowledge about the system (architecture
concepts, capability maps, module summaries, domain terms) that agents consult **before**
exploring the repository. This capability is the live home of the context-minimization rules in
[ADR-A-0003](../../../adrs/agentic/ADR-A-0003-context-minimization.md): the cheapest context is
the context someone already summarized.

## Canonical format: OKF

The canonical on-disk format is the
[Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf):
plain markdown files with YAML frontmatter (`type`, `resource`, `tags`, `timestamp`), an
`index.md` per directory for progressive disclosure, and cross-links between concepts forming a
graph. It is vendor-neutral, git-versioned, and readable by every supported agent framework
without an SDK — the same idiom the rest of the boilerplate uses for skills, ADRs, and specs.

The default provider is an in-repo bundle at [`knowledge/`](../../../knowledge/README.md).

## Mandatory context sequence

Agents load context in this order and **stop at the shallowest level that answers the
question** ("graph before grep"):

| Level | Load | Stop here when you know… |
|-------|------|--------------------------|
| 0 | The ticket / context packet | goal, scope, embedded excerpts suffice |
| 1 | `knowledge/index.md` | which concept owns the question |
| 2 | The owning concept file | applicable rules, affected capability |
| 3 | Concept files it cross-links | contracts between capabilities |
| 4 | Source files **named** by the ticket or a concept | implementation detail |
| 5 | Broad grep / full-file exploration | *last resort — declare it as an overrun in the handoff record, with a reason* |

Skipping levels 1–4 and going straight to broad exploration is a gate-relevant workflow
violation when this capability is configured (ADR-A-0003).

## Operations (all providers MUST implement)

| Operation | Semantics |
|-----------|-----------|
| `list_index()` | Return the top-level index (concept names + one-line summaries). |
| `get_concept(name)` | Return one concept document. |
| `get_excerpt(name, question?)` | Return a summarized excerpt suitable for embedding in a ticket. |
| `search(query)` | Locate concepts by frontmatter fields or text. |
| `refresh(scope)` | Re-derive concept files affected by a merged change set. |

For the `okf-repo` provider these are plain file operations — no tooling required.

## Providers

- **`okf-repo`** (neutral default) — the bundle lives in-repo under `knowledge/`; agents read
  it directly; `refresh` = a docs PR through the standard human-merge gate.
- **`graphify`, `codebase-memory`** — context-graph MCPs; must expose the same operations and
  should export/import OKF so the bundle stays portable.
- **`none`** — supported; agents fall back to pattern discovery and ticket excerpts only, and
  the graph-before-grep gate does not apply.

## Who uses it

- **Ticket creation (BSA)** pulls `get_excerpt` output into tickets so coding agents don't
  re-derive context — "excerpts over rediscovery": cost paid once at ticket creation, saved N
  times at execution.
- **Implementation/review agents** follow the mandatory context sequence above.
- **Documentation workflow (tech-writer / `update-docs`)** runs `refresh` after merges so
  concept files track the code; a stale bundle is a documentation defect like any other.
