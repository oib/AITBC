# v0.16.2 — Platform Builder Tooling (Phase 2: SDK & White-Label)

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Deliver the Platform Builder SDK, SDK reference docs, and
white-label/plugin architecture on top of the v0.16.1 builder foundation.

**Prerequisites**: v0.16.1 complete; v0.17.0 planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/types/`, `packages/py/aitbc-sdk/` | SDK shared types, Python SDK package |
| **Agent B** | `cli/`, `docs/builders/`, `packages/aitbc-core`, `apps/website` | White-label CLI commands, SDK reference docs, headless core extraction, plugin manifest |

---

## Agent A — Shared Core & SDK Types

### A1: SDK shared types (P0)

- File: `aitbc/types/sdk.py` (new)
  - Lightweight request/response models for the SDK client.
- File: `aitbc/types/grant.py` (new or update)
  - `GrantProposal`, `GrantMilestone`, `DeveloperProfile` data classes.

### A2: SDK package (P0)

- File: `packages/py/aitbc-sdk/pyproject.toml` (new)
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/__init__.py` (new)
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/client.py` (new)
  - High-level coordinator-api, wallet, and registry clients.
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/retry.py` (new)
  - Shared retry and circuit-breaker helpers.

---

## Agent B — White-Label, Docs & CLI

### B1: SDK reference documentation (P0)

- File: `docs/builders/sdk-reference.md` (new)
  - API client usage examples.

### B2: White-label architecture (P1)

- File: `packages/aitbc-core/` (refactor/extract)
  - Headless logic provider decoupled from `apps/website` and `apps/coordinator-api`.
- File: `packages/aitbc-core/manifest/brand.py` (new)
  - Brand manifest schema (logos, themes, endpoints, settlement rules, bonds).

### B3: Plugin architecture (P1)

- File: `packages/aitbc-core/plugins/manifest.py` (new)
  - Plugin manifest and lifecycle hooks.
- File: `packages/aitbc-core/plugins/loader.py` (new)
  - Dynamic loading of `onResourceDiscovery`, `onNegotiationStart`,
    `onProofGeneration`, and `onVerificationSuccess` hooks.

### B4: White-label CLI commands (P1)

- File: `cli/aitbc_cli/commands/platform.py` (new)
  - `aitbc init-platform --name --template`.
- File: `cli/aitbc_cli/commands/plugin.py` (new)
  - `aitbc plugin create --type --name`.
- File: `cli/aitbc_cli/commands/deploy.py` (new or update)
  - `aitbc deploy-brand --config --network --storage`.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Coordination Protocol

- Agent A owns `aitbc/types/sdk.py`, `aitbc/types/grant.py`, and the
  `packages/py/aitbc-sdk/` Python package.
- Agent B owns white-label extraction into `packages/aitbc-core/`, plugin
  manifests, CLI scaffolding commands, and SDK reference docs.
- Shared boundary: `aitbc/types/sdk.py` and `aitbc/types/grant.py` are consumed
  by `packages/py/aitbc-sdk/` and `apps/coordinator-api`; Agent A lands them
  before Agent B wires the SDK clients and white-label commands.
- Sequence: Agent A lands SDK types and package scaffold before Agent B adds
  white-label CLI commands and plugin hooks.

## Release Gate

- [ ] `aitbc-sdk` package installs and exposes a coordinator-api client.
- [ ] SDK reference documentation covers all public client methods.
- [ ] White-label brand manifest is documented and has an example.
- [ ] Plugin lifecycle hooks are wired into OpenClaw agent execution.
- [ ] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
