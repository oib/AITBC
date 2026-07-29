# Docs Adapter — Interface

Durable, human-facing documentation: specs, ADRs, guides, release notes. Agents publish and
update docs through this capability rather than assuming a specific tool.

## Operations

| Operation | Semantics |
|-----------|-----------|
| `get_page(id)` | Fetch a document/page. |
| `create_page(space, title, body, parent?)` | Create a doc; return id. |
| `update_page(id, body)` | Update content (versioned by the provider). |
| `link(id, target)` | Cross-link docs, tickets, PRs. |
| `search(query)` | Locate existing docs before writing new ones (reuse-first). |

## Providers

- **`confluence`** (saw-stack) — backed by SAW's `confluence-docs` skill, the `tech-writer`
  agent, and `confluence-mcp`. `BLUEPRINT.md` is written to be import-friendly:
  each H2 maps to one Confluence child page.
- **`markdown-repo`** — docs live in-repo under `docs/`; "publish" = a docs PR. Zero external
  dependency; the neutral default when no docs tool is configured.
- **`notion`, `none`** — pluggable / disabled.

The Documentation workflow updates only docs affected by merged scope, and ships them as their
own small PRs through the standard human-merge gate.
