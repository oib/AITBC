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

### A1: SDK shared types + installable package (P0) — ✅ complete

- File: `aitbc/types/sdk.py` (new)
  - `SDKRequest`, `SDKResponse`, `WalletBalance`, `RegistryEntry`, and
    `GrantSummary` lightweight request/response models.
- File: `aitbc/types/grant.py` (existing from v0.16.1)
  - `GrantProposal`, `GrantMilestone`, `DeveloperProfile` data classes.
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/client.py` (new)
  - `CoordinatorAPIClient` (also exported as `AITBCClient`) with nested
    `WalletClient` and `RegistryClient`.
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/errors.py` (new)
  - `AITBCError`, `AITBCConnectionError`, `AITBCRateLimitError`.
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/retry.py` (updated)
  - `with_backoff` helper and `SDKRetryPolicy` / `SDKCircuitBreaker` wrappers.

### A2: SDK package (P0) — ✅ complete

- File: `packages/py/aitbc-sdk/pyproject.toml` (new)
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/__init__.py` (updated)
  - Lazy exports for `CoordinatorAPIClient`/`CoordinatorClient`, `WalletClient`,
    `RegistryClient`, `SDKRetryPolicy`, `SDKCircuitBreaker`, `with_backoff`, and
    SDK exception types.
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/client.py` (new)
  - High-level `CoordinatorAPIClient` (coordinator-api, wallet, and registry),
    `WalletClient`, and `RegistryClient`.
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/retry.py` (new)
  - `SDKRetryPolicy`, `SDKCircuitBreaker`, and `with_backoff` helpers.
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/errors.py` (new)
  - SDK-specific exception types (`AITBCError`, `AITBCConnectionError`,
    `AITBCRateLimitError`).

---

## Agent B — White-Label, Docs & CLI

### B1: SDK reference documentation (P0) — ✅ complete

- File: `docs/builders/sdk-reference.md` (new)
  - Covers installation, coordinator/wallet/registry client examples, error
    handling, shared SDK types, and the `aitbc-core` white-label package.

### B2: White-label architecture (P1) — ✅ complete

- File: `packages/aitbc-core/` (new)
  - Headless logic provider with `pyproject.toml` and the `aitbc_core` package.
- File: `packages/aitbc-core/aitbc_core/manifest/brand.py` (new)
  - `BrandManifest`, `BrandAssets`, and `SettlementRules` schemas with
    `to_dict()` serialization.

### B3: Plugin architecture (P1) — ✅ complete

- File: `packages/aitbc-core/aitbc_core/plugins/manifest.py` (new)
  - `PluginManifest` and `PluginHookRegistry` for the four lifecycle hooks.
- File: `packages/aitbc-core/aitbc_core/plugins/loader.py` (new)
  - Dynamic loading of plugins by `entry_point` string.

### B4: White-label CLI commands (P1) — ✅ complete

- File: `cli/aitbc_cli/commands/platform.py` (new)
  - `aitbc platform init-platform --name --template --output`.
- File: `cli/aitbc_cli/commands/plugin.py` (new)
  - `aitbc plugin create --type --name --output`.
- File: `cli/aitbc_cli/commands/deploy.py` (new)
  - `aitbc deploy deploy-brand --config --network --storage`.
- `tests/unit/test_v162_agent_b.py` covers brand manifests, plugin hooks/loader,
  and the three new CLI commands.

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

- [x] `aitbc-sdk` package installs and exposes a coordinator-api client.
- [x] SDK reference documentation covers all public client methods.
- [x] White-label brand manifest is documented and has an example.
- [x] Plugin lifecycle hooks are wired into OpenClaw agent execution.
- [x] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
