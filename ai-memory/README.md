# AI Memory — Structured Knowledge for Autonomous Agents

This directory implements a hierarchical memory architecture to improve agent coordination and recall.

## Layers

- **daily/** – chronological activity logs (append-only)
- **architecture/** – system design documents
- **decisions/** – recorded decisions (architectural, protocol)
- **failures/** – known failure patterns and debugging notes
- **knowledge/** – persistent technical knowledge (coding standards, dependencies, environment)
- **agents/** – agent-specific behavior and responsibilities

## Usage Protocol

Before starting work:
1. Read `architecture/system-overview.md` and relevant `knowledge/*`
2. Check `failures/` for known issues
3. Read latest `daily/YYYY-MM-DD.md`

After completing work:
4. Append a summary to `daily/YYYY-MM-DD.md`
5. If new failure discovered, add to `failures/`
6. If architectural decision made, add to `decisions/`

This structure prevents context loss and repeated mistakes across sessions.