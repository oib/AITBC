# AITBC v0.19.0 Release Notes

**Date**: 2026-07-30
**Status**: Complete (unpushed)
**Scope**: v0.18.0 Agent B completion, SAW harness v2.35.0, Gitea tracker adapter, AITBC-60 retro & dependency/security audit fixes
**Baseline**: v0.18.0 (commit `a122f6fbe`)
**Commits since baseline**: 20
**Files changed**: 1,545
**Lines**: +2,694,091 / -1,183

## Overview

v0.19.0 wraps the work since the v0.18.0 release plan. It completes the v0.18.0 application-side audit remediation, adopts the SAW v2.35.0 agentic harness, adds a Gitea Issues tracker adapter, and documents the AITBC-60 dependency/security audit retro.

## Major Changes

### 1. v0.18.0 Agent B audit remediation (complete)

The remaining Agent B tasks from `docs/releases/v0.18/v0.18.0_AGENTS.md` are now implemented:

- `import_block` validation and 409 handling for conflicting hashes
- `import_chain` admin auth and atomic transaction wrapping
- Block signature verification and PBFT signature gating
- Deterministic validator rotation and mempool eviction tiebreakers
- Persistent replay protection for transactions and bridge proofs
- Bridge/HTLC nonce correctness
- Settlement robustness and bridge-monitor fund safety
- `Decimal` money migration and trading settlement/matching locking
- Missing database rollbacks
- Auth defaults, SSRF address validation, and timing-safe login
- SQLite context-manager robustness and timezone fixes

**Files**: 89 files under `apps/`, plus `aitbc/` and `cli/`

### 2. SAW harness v2.35.0 adoption

The repo now runs on SAFe Agentic Workflow (SAW) v2.35.0:

- `.claude/`, `.gemini/`, `.codex/`, `.cursor/`, `.agents/`, `harness/`, `dark-factory/`, `knowledge/`, `patterns_library/`, `adrs/`, `profiles/`, `blueprint/`, `specs/`
- `tests/run-all.sh` harness self-test suite
- `graphify-out/` knowledge graph
- `.harness-manifest.yml`, `.harness-manifest.schema.json`, `INTEGRATION.md`
- `vendor/impeccable/`

### 3. Gitea Issues tracker adapter

- New `scripts/gitea-tracker.sh`
- Fixes for empty-field row corruption in `search` and `children` output

### 4. AITBC-60 dependency and security audit retro

- `poetry.lock`, `pyproject.toml`, `requirements.txt` updates:
  - `msgpack` 1.1.2 -> 1.2.1
  - `pydantic-settings` 2.14.1 -> 2.14.2
  - `starlette` 1.2.1 -> 1.3.1
- 107 bandit findings resolved to 0 across `aitbc/`, `apps/`, `cli/`
- Retro documentation in `work/improvement-proposals/2026-07-29-*.md` and `docs/agent-outputs/technical-docs/dependency-audit-report-2026-07-29.md`

## Statistics

- 1,545 files changed
- 2,694,091 insertions, 1,183 deletions
- 20 commits since the v0.18.0 baseline
- 14 of those commits are currently on `main` but not on `origin/main`

## Security Summary

- `msgpack` DoS on repeated `Unpacker` error — fixed via upgrade
- `pydantic-settings` secrets-dir symlink escape — fixed via upgrade
- `starlette` URL reconstruction and form-size-limit bypass — fixed via upgrade
- `ecdsa` Minerva timing attack — investigated, no exploitable path found
- 107 bandit findings triaged to 0
- New auth defaults, SSRF validation, timing-safe comparisons, and rollback hygiene

## Known Issues

- `main` is 14 commits ahead of `origin/main`; the v0.19.0 deliverable is committed but not yet pushed.
- `CLAUDE.md` has uncommitted working-tree modifications.
- Several `work/.gitea-events-state.current.*` temp files are present.
- The orchestrator's local-main-drift sensor logs to `work/.orchestrator/run.log` only when no notify ticket is configured (documented in `work/improvement-proposals/2026-07-29-local-main-drift-notify-sink.md`).

## Documentation

- `docs/releases/v0.19/v0.19.0_AGENTS.md` — full agent split and release gate
- `docs/releases/v0.19/RELEASE_v0.19.0.md` — this file

## Verification

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
./venv/bin/python -m pytest tests/integration -q -o addopts=""
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
cd apps/blockchain-node && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
bash tests/run-all.sh
```

---

*Generated with [Devin](https://devin.ai)*
