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
├── packages/
├── scripts/
├── tests/
├── website/
├── build/            # generated output
└── venv/             # local virtualenv
```

### Main directories at a glance

- **`apps/`** — application and service packages
- **`cli/`** — CLI entrypoints and command modules
- **`contracts/`** — Solidity contracts and deployment tooling
- **`dev/`** — developer utilities and local helpers
- **`docs/`** — documentation tree, including `getting-started/`, `infrastructure/`, `reference/`, `deployment/`, `features/`, `scenarios/`, and `archive/`
- **`packages/py/`** — shared Python libraries (`aitbc-agent-core`, `aitbc-agent-sdk`, `aitbc-crypto`, `aitbc-errors`, `aitbc-sdk`); `aitbc-core` lives at `packages/aitbc-core/`
- **`scripts/`** — CI, deployment, development, monitoring, service, testing, utility, and wrapper scripts
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
