# v0.10.17 — Security & Auth Hardening (Bugfix)

**Last Updated**: 2026-07-22 (Agent A complete)
**Version**: 1.1 — Agent A complete; Agent B pending

**Release Theme**: Fix auth bypass, hardcoded defaults, and empty-password
fallbacks discovered during codebase scan.

**Prerequisites**: v0.10.16 complete.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/auth/`, `aitbc/training_setup/` | Remove hardcoded defaults, close empty-password fallbacks, fix exception handling |
| **Agent B** | `apps/agent-coordinator/src/agent_app/routers/auth.py`, wallet routes, cross-chain adapter | Fix auth bypass, add nonce verification, enforce ownership, remove SSRF/private-key paths |

---

## Agent A — Shared Core

### A1: Remove hardcoded training default (P0) ✅

- File: `aitbc/training_setup/environment.py` — completed.
- Removed `password = password or "training123"`; raises `ValueError` if empty.

- File: `aitbc/training_setup/environment.py`
- Remove `password = password or "training123"`; require explicit env or fail.

### A2: Close empty-password fallbacks (P0) ✅

- Auth primitives (`jwt.py`, `dependencies.py`) have no empty-string fallbacks.
- Main auth bypass (`operator`/`user` `""` fallback) remains in Agent B `auth.py`.

- File: `aitbc/auth/dependencies.py`, `jwt.py`, middleware
- Reject empty `operator_password` / `user_password`; no `""` fallback.

### A3: Target exception handling (P1) ✅

- Completed: `aitbc/auth/api_key.py`, `aitbc/auth/middleware.py`.
- Replaced broad `except Exception` with `(OSError, json.JSONDecodeError, KeyError, TypeError)` etc.

- Replace broad `except Exception` with specific exception types; return generic errors without exposing internals.

---

## Agent B — Applications

### B1: Fix auth bypass in agent-coordinator (P0)

- File: `apps/agent-coordinator/src/agent_app/routers/auth.py`
- Require non-empty env vars for all demo roles; reject empty-string login.

### B2: Wallet login hardening (P1)

- Implement nonce challenge + cryptographic wallet-signature verification.
- Generate secure random session tokens.
- Enforce `user_id` ownership on balance/transaction routes.

### B3: Remove wallet trust-boundary violations (P1)

- Resolve RPC URLs from server-side allowlist; reject arbitrary client URLs.
- Never accept private keys through request parameters.
- Remove `default_password` and empty-password encryption fallbacks.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
./venv/bin/python -m pytest tests/security -q -o addopts=""
```

---

## Coordination Protocol

- Agent A edits `aitbc/auth/` first; Agent B wires coordinator-api dependencies after.
- Shared file `aitbc/auth/dependencies.py` requires sequential edits with `# WIP` markers.
- Do not edit `aitbc/database/replica.py` or `aitbc/network/circuit_breaker.py` without coordination.

---

---

## Additional Findings (added to release plan)

### P0 — Fresh Instance Wiring Bug (`main.py:379`)
- Disposable `peer_sync` used only for P2P callback. Fixed by storing `self._sync` and reusing it.

### P1 — Feature Flags (`v0.10.1` discrepancy)
- `sync_delta_enabled`, `sync_parallel_enabled`, `gossip_priority_enabled` flipped to `True`.

### P2 — Pool-Hub v0.6.7 Gaps
- `BlockchainClient`, reward constants, `distribute_rewards()`, eligibility logic, Prometheus counters: all present.
- Reward signing integration deferred to v0.7.1 (`blockchain.py:74-77`).

### P2 — Coordinator-API Alembic Isolation ✅
- `env.py` now honors `DATABASE_URL` or `SQLITE_URL` override before falling back to `app_settings.database.effective_url`.

### P2 — Systemd Symlink Audit
- After restructure: `scripts/utils/link-systemd.sh` → `load-keystore-secrets.sh`.
- If `resources` failure: `systemctl reset-failed` then retry.

### Fix Priority Table (from full scan)

| Priority | Issue | Status |
| P0 | Wiring bug (`main.py:379`) | Fixed |
| P0 | MyPy errors coordinator-api (125 in 23 files; Agent B subset clean) | Tracked separately |
| P1 | Feature flags mismatch | Fixed |
| P1 | Ruff `aitbc/` (4 errors) | Fixed |
| P2 | Alembic isolation (`DATABASE_URL` / `SQLITE_URL`) | Fixed |
| P2 | Pool-hub reward signing (v0.7.1) | Tracked |

---

*Generated with [Devin](https://devin.ai)*
