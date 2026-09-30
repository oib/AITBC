# AITBC Repository File Structure

This document describes the current organization and status of files and folders in the repository. A current snapshot appears first, followed by a short list of related docs.

Last updated: 2026-09-30

## Current Snapshot

This is the authoritative layout of the repository root at `/opt/aitbc`.

```text
/opt/aitbc/
├── aitbc/            # core shared Python package
├── apps/
├── cli/
├── contracts/
├── docs/
├── examples/
├── mcp-server/
├── packages/
├── plugins/
├── scripts/
├── skills/
├── tests/
├── website/
└── venv/             # local virtualenv
```

### Main directories at a glance

- **`aitbc/`** — the core shared Python package (crypto, caching, database, network, oracles, …)
- **`apps/`** — application and service packages
- **`cli/`** — CLI entrypoints and command modules
- **`contracts/`** — Solidity contracts and deployment tooling
- **`docs/`** — documentation tree, including `getting-started/`, `infrastructure/`, `reference/`, `deployment/`, `features/`, `scenarios/`, and `archive/`
- **`mcp-server/`** — the MCP server exposing node operations to agents
- **`packages/py/`** — shared Python libraries (`aitbc-agent-core`, `aitbc-agent-sdk`, `aitbc-crypto`, `aitbc-errors`, `aitbc-sdk`); `aitbc-core` lives at `packages/aitbc-core/`
- **`plugins/`** — plugin entry points
- **`scripts/`** — CI, deployment, development, monitoring, service, testing, utility, and wrapper scripts
- **`skills/`** — agent skill definitions
- **`tests/`** — repository-wide test suites and fixtures
- **`website/`** — public site, dashboards, docs portal, and wallet assets

### Notes

- **Repo root**: `/opt/aitbc`
- **Legacy home paths**: historical only
- **Deployment docs**: see `docs/deployment/` and `docs/infrastructure/`

---

## See Also

- `docs/deployment/`
- `docs/infrastructure/`
- `docs/getting-started/`

This page intentionally stays short. For detailed historical context, use the infrastructure and completed-deployments docs above.
