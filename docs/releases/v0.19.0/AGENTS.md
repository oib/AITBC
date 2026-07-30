# v0.19.0 — SAW v2.35.0, Gitea Tracker, AITBC-60 Retro & v0.18.0 B Completion

**Last Updated**: 2026-07-30
**Version**: 0.1 — Release complete (unpushed)
**Changelog**: [RELEASE_v0.19.0.md](RELEASE_v0.19.0.md)

**Release Theme**: Complete the remaining v0.18.0 Agent B audit-remediation work, adopt the SAW v2.35.0 harness, introduce the Gitea Issues tracker adapter, and document the AITBC-60 dependency/security audit retro.

**Prerequisites**: v0.18.0 (commit `a122f6fbe`)

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `.claude/`, `.agents/`, `.gemini/`, `.cursor/`, `.codex/`, `harness/`, `dark-factory/`, `knowledge/`, `patterns_library/`, `adrs/`, `profiles/`, `blueprint/`, `specs/`, `vendor/impeccable/`, `tests/` (harness suite), `scripts/` (gitea-tracker), `docs/`, `work/improvement-proposals/` | SAW v2.35.0 adoption, harness self-test suite, gitea-tracker adapter, AITBC-60 retro documentation |
| **Agent B** | `apps/`, `aitbc/`, `cli/`, `poetry.lock`, `pyproject.toml`, `requirements.txt` | v0.18.0 B1–B16 completion, dependency CVE fixes, bandit triage 107 -> 0 |

**No file overlap between agents.** `packages/py/aitbc-agent-sdk` carries the v0.18.0 SDK task-reference fixes and is treated as Agent A for consistency with v0.18.0.

---

## Agent A — Neutral Harness, Docs & Tracker

### A1: SAW harness v2.35.0 adoption

- **Files**: top-level harness directories and the restored `tests/` harness suite.
- **What changed**:
  - Adopt SAW v2.35.0 (`.claude/`, `.agents/`, `.gemini/`, `.cursor/`, `.codex/`, `harness/`, `dark-factory/`, `knowledge/`, `patterns_library/`, `adrs/`, `profiles/`, `blueprint/`, `specs/`, `vendor/impeccable/`).
  - Generate the `graphify-out/` knowledge graph.
  - Restore and green the full harness self-test suite (`tests/run-all.sh`).
  - Resolve slash-command and template gaps.
- **Neutral core overlay**: add `INTEGRATION.md`, `.harness-manifest.yml`, and `.harness-manifest.schema.json` mapping SAW's execution layer to the repo's technology-agnostic profiles.

### A2: Gitea Issues tracker adapter

- **Files**: `scripts/gitea-tracker.sh` (new)
- **What changed**:
  - Add `gitea-tracker.sh` as a neutral task-tracking adapter for Gitea Issues.
  - Fix empty-field row corruption in `gitea-tracker.sh search` and `children` output.

### A3: AITBC-60 retro and consumer feedback

- **Files**:
  - `work/improvement-proposals/2026-07-29-local-main-drift-notify-sink.md`
  - `work/improvement-proposals/2026-07-29-security-audit-skill-stack-mismatch.md`
  - `work/improvement-proposals/2026-07-29-skill-proposals-security-audit-remediation.md`
  - `work/consumer-feedback/2026-07-29-aitbc.csv`
  - `docs/agent-outputs/technical-docs/dependency-audit-report-2026-07-29.md`
- **What changed**: document the local-main-drift notify sink, the security-audit skill stack mismatch, and the skill proposals derived from the AITBC-60 epic; export consumer-feedback CSV.

---

## Agent B — Application Hardening & Dependency Audit

### B1–B16: v0.18.0 Agent B audit remediation completion

- **Files**: `apps/blockchain-node/`, `apps/bridge-monitor/`, `apps/trading/`, `apps/marketplace/`, `apps/wallet/`, `apps/api-gateway/`, `apps/coordinator-api/`, `apps/agent-coordinator/`, `apps/gpu/`, `apps/blockchain-explorer/`, `apps/pool-hub/`
- **What changed**: complete the remaining v0.18.0 B-side tasks.
  - B1/B2: `import_block`/`import_chain` validation and rollback correctness.
  - B3: block signature verification and PBFT signature gating.
  - B4: deterministic validator rotation and mempool eviction tiebreakers.
  - B5: persistent replay protection for transactions and bridge proofs.
  - B6: bridge/HTLC nonce correctness.
  - B7/B8: settlement robustness and bridge-monitor fund safety.
  - B9/B10: `Decimal` money migration and trading settlement/matching locking.
  - B11: missing database rollbacks.
  - B12/B13: auth defaults and SSRF address validation.
  - B14: timing-safe login comparison.
  - B15: robustness sweep (SQLite context managers, billing transaction, HIPAA timezone fix).
  - B16: P2 follow-ups tracked in `blockchain-node`.
- **Verification**: per-task regression tests live in `apps/blockchain-node/tests/`. See `docs/releases/v0.18.0/AGENTS.md` for the original detailed acceptance criteria.

### B17: Dependency and security audit resolution

- **Files**: `poetry.lock`, `pyproject.toml`, `requirements.txt`, `aitbc/config/hierarchical_config.py`, `aitbc/oracles/price_oracle.py`, `apps/*/`, `cli/aitbc_cli/commands/market/jobs.py`
- **What changed**:
  - Upgrade `msgpack` 1.1.2 -> 1.2.1 (GHSA-6v7p-g79w-8964)
  - Upgrade `pydantic-settings` 2.14.1 -> 2.14.2 (GHSA-4xgf-cpjx-pc3j)
  - Upgrade `starlette` 1.2.1 -> 1.3.1 (PYSEC-2026-248, PYSEC-2026-249)
  - Investigate `ecdsa` 0.19.2 Minerva timing attack (PYSEC-2026-1325) — no exploitable path found.
  - Resolve 107 bandit findings to 0 across `aitbc/`, `apps/`, `cli/` through fixes and `# nosec` justifications.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
./venv/bin/python -m pytest tests/integration -q -o addopts=""
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
cd apps/blockchain-node && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
bash tests/run-all.sh
pip-audit --desc 2>/dev/null || true
bandit -r aitbc apps cli 2>/dev/null || true
```

## Release Gate

- [ ] v0.18.0 B1–B16 regression tests pass.
- [ ] SAW harness `tests/run-all.sh` passes.
- [ ] `gitea-tracker.sh search` and `children` produce uncorrupted rows.
- [ ] `pip-audit` shows only the unfixable `ecdsa` advisory.
- [ ] `bandit -r aitbc apps cli` shows 0 findings.
- [ ] `ruff check .`, `mypy aitbc/`, unit + integration suites green.
- [ ] Local `main` drift resolved and the v0.19.0 commits pushed to `origin/main`.

*Generated with [Devin](https://devin.ai)*
