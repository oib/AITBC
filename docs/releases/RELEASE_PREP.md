# Release Preparation Checklist (Pre-Code)

Use this checklist before starting implementation on any release to avoid
merge conflicts, broken CI, and unclear ownership.

## 1. Working Tree Hygiene

- [ ] `git status` is clean or all uncommitted changes are intentionally
      staged/committed.
- [ ] No untracked `plugins/`, `packages/py/aitbc-agent-core/`, or `apps/`
      spikes are left over from previous sessions.
- [ ] `./venv/bin/python -m ruff check .` passes on `main`.
- [ ] `./venv/bin/python -m mypy --show-error-codes aitbc/` passes on `main`.
- [ ] `./venv/bin/python -m pytest tests/unit -q -o addopts=""` passes on `main`.

## 2. Release Order & Dependencies

Order matters because later releases consume shared types from earlier ones:

```
v0.10.18  (update deployment stabilization) ✅ complete
  → v0.11.0  (Phase 4 & 2026 roadmap foundations: memory, economics, grants, compliance) 🚧 in progress
  → v0.12.0  (OpenClaw Autonomous Economics) 🚧 planned
  → v0.13.0  (Mature Autonomous Economic Infrastructure) 🚧 planned
  → v0.14.1  (TEE-Backed Verification & Confidential Compute Phase 1) 🚧 planned
  → v0.14.2  (TEE-Backed Verification & Confidential Compute Phase 2) 🚧 planned
  → v0.15.1  (Compliance-Ready Modules Phase 1: policies, encryption, audit, HIPAA) 🚧 planned
  → v0.15.2  (Compliance-Ready Modules Phase 2: containers, finance, middleware, CLI) 🚧 planned
  → v0.16.1  (Platform Builder Tooling Phase 1: CLI config, registry, grants, local dev) 🚧 planned
  → v0.16.2  (Platform Builder Tooling Phase 2: SDK, white-label/plugin architecture) 🚧 planned
  → v0.17.0  (Accessibility & Theme Engine) 🚧 planned
  → v1.0.0   (production readiness)
  → v2.0.0   (vision — questionable features, parked for re-evaluation)
```

## 3. Shared Design Documents

Before code, write or review design docs for any cross-cutting types:

- `v0.11.0` — Agent Memory State Tree (AMST), content addressing, encryption
  envelope.
- `v0.12.0` / `v0.13.0` — Agent wallet/escrow, bond state machine, pricing
  strategies.
- `v0.15.1` / `v0.15.2` — Data classification, consent, retention, audit log
  schema.
- `v0.14.1` / `v0.14.2` — TEE quote format, attestation API, sealing key flow.
- `v0.16.1` / `v0.16.2` — SDK JSON-RPC/WebSocket contracts, plugin manifest
  schema.

## 4. Agent Coordination

- [ ] Declare shared-file edits in the release `AGENTS.md` "Coordination"
      section.
- [ ] Sequence shared files per the root `AGENTS.md` protocol:
  - Agent A first for `aitbc/` shared files.
  - Agent B first for `apps/` shared files.
  - Lock files with a `# WIP: Agent X` comment while editing.
- [ ] Review conflict boundaries:
  - `aitbc/database/replica.py`
  - `aitbc/network/circuit_breaker.py`
  - `aitbc/agent_bridge/`
  - `apps/blockchain-node/src/aitbc_chain/rpc/router.py`
  - `apps/blockchain-node/src/aitbc_chain/sync.py`

## 5. Feature Flags & Branching

- [ ] Each major release has a feature flag (e.g., `MEMORY_ENABLED`,
      `AGENT_ECONOMICS_ENABLED`, `TEE_ENABLED`) defaulting to `False`.
- [ ] Release work is done on a branch or behind the flag so `main` stays
      deployable.
- [ ] Database migrations are Alembic `if_not_exists=True` and reversible.

## 6. CI & Verification Baseline

- [ ] `./venv/bin/python -m ruff check .` passes.
- [ ] `./venv/bin/python -m mypy --show-error-codes aitbc/` passes.
- [ ] `./venv/bin/python -m pytest tests/unit -q -o addopts=""` passes.
- [ ] Coordinator-api migrations (`alembic upgrade head` and `alembic check`)
      pass.

## 7. Security & Compliance Pre-Checks

- [ ] `scripts/security/scan_secrets.py` reports no hardcoded keys.
- [ ] No new dependencies are less than 7 days old.
- [ ] `v0.15.1` / `v0.15.2` and `v0.14.1` / `v0.14.2` security review/audit slots are scheduled.

## 8. Stub Skeletons

- [ ] Create empty `__init__.py` and `py.typed` files for new `aitbc/`
      packages so downstream imports resolve while types are still being
      written.

## 9. Public API Freeze

- [ ] `v0.16.2` SDK/white-label public JSON-RPC and WebSocket contracts are
      documented before implementation.
- [ ] `coordinator-api` route changes are backwards-compatible or versioned.

## 10. Release Gate Sign-Off

- [ ] Release gate checklist in `docs/releases/<version>/change.log` is reviewed
      and realistic.
- [ ] `AGENTS.md` task split is assigned and does not overlap with other
      in-flight releases.
- [ ] `docs/releases/STATUS.md` is updated to reflect the release state.
