# AITBC Repository File Structure

This document describes the current organization and status of files and folders in the repository. A current snapshot appears first, followed by a short list of related docs.

Last updated: 2026-04-27

## Current Snapshot

This is the authoritative layout of the repository root at `/opt/aitbc`.

```text
/opt/aitbc/
├── apps/
├── cli/
├── contracts/
├── dev/
├── docs/
├── examples/
├── extensions/
├── infra/
├── packages/
├── plugins/
├── scripts/
├── systemd/
├── tests/
├── website/
├── build/            # generated output
├── venv/             # local virtualenv
└── agent_registry.db # runtime database
```

### Main directories at a glance
- **`apps/`** — application and service packages
- **`cli/`** — CLI entrypoints and command modules
- **`contracts/`** — Solidity contracts and deployment tooling
- **`dev/`** — developer utilities and local helpers
- **`docs/`** — documentation tree, including `beginner/`, `project/`, `infrastructure/`, `reference/`, and `workflows/`
- **`packages/py/`** — shared Python libraries (`aitbc-agent-sdk`, `aitbc-core`, `aitbc-crypto`, `aitbc-sdk`)
- **`plugins/`** — plugin integrations such as Ollama
- **`scripts/`** — CI, deployment, development, monitoring, service, testing, utility, and wrapper scripts
- **`systemd/`** — standardized service units
- **`tests/`** — repository-wide test suites and fixtures
- **`website/`** — public site, dashboards, docs portal, and wallet assets

### Notes
- **Repo root**: `/opt/aitbc`
- **Legacy home paths**: historical only
- **Deployment docs**: see `docs/beginner/02_project/3_infrastructure.md` and `docs/beginner/02_project/5_done.md`

---

## See Also

- `docs/beginner/02_project/3_infrastructure.md`
- `docs/beginner/02_project/5_done.md`
- `docs/beginner/README.md`

This page intentionally stays short. For detailed historical context, use the infrastructure and completed-deployments docs above.
