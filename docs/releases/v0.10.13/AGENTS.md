# v0.10.13 — Agent Task Assignment

**Last Updated**: 2026-07-14
**Version**: 1.0 — Security & Correctness Hardening

**Release Theme**: Post-v0.10.12 security and correctness hardening — address the highest-confidence findings from the deep audit: committed credentials, missing authentication on financial/admin routes, unsigned marketplace transactions, fake payment success paths, forgeable wallet/FHE/audit signatures, broken Web3 compatibility, file/DB permission leaks, and migration/test blind spots.

**Goal**: Close the trust-boundary and correctness gaps identified in the post-v0.10.12 audit so the coordinator-api, blockchain-node, and shared core can move toward production readiness.

> **Scope**: 14 focus tasks split across Agent A (shared core) and Agent B (apps, scripts, CLI, tests). No new user-facing features; fixes are security/correctness only.
> **Prerequisites**: [v0.10.12](../v0.10.12/change.log) (✅ complete).
> **Risk**: High. Several fixes change previously permissive behavior (auth on routes, signature enforcement, payment failures). Document any intentional breaking changes in the release notes.

---

## Task Split Overview

| Agent | Domain | Tasks | Focus |
|-------|--------|-------|-------|
| **Agent A** | Type safety & shared core (`aitbc/`) | 3 | Web3 7.x fix, Alembic metadata reconciliation, async DB URL parsing |
| **Agent B** | Infrastructure & apps (`apps/`, `scripts/`, `cli/`, `tests/`) | 11 | Credential hygiene, auth, signatures, payments, wallet/FHE, file permissions, staking/quota/governance, test/CI blind spots |

**Conflict boundary**: Agent A owns `aitbc/network/web3_utils.py`. `SQLModel.metadata` and Alembic versions touch both shared core registration and coordinator-api models — sequence through the coordination log. Agent B owns apps and scripts.

---

## Agent A — Type Safety & Shared Core

**Scope**: Fix shared-core issues that break downstream app behavior and migration tooling.

**Working directory**: `/opt/aitbc/`

**Verification commands**:

```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/
cd /opt/aitbc && ./venv/bin/python -m ruff check aitbc/
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Fix Web3 7.x `geth_poa_middleware` import | 🔴 P0 | `aitbc/network/web3_utils.py` | ✅ |
| A2 | Reconcile `SQLModel.metadata` with the Alembic migration graph | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/storage/db.py`, `apps/coordinator-api/alembic/versions/`, `apps/coordinator-api/src/coordinator_api/contexts/*/domain/*.py`, `tests/unit/test_v0519_tech_debt.py` | ✅ |
| A3 | Fix `database_async.py` async URL conversion | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/database_async.py` | ✅ |

### Agent A — Detailed Instructions

#### A1: Fix Web3 7.x `geth_poa_middleware` import

**Problem**: `aitbc/network/web3_utils.py` imports `geth_poa_middleware` from `web3.middleware`. In Web3.py 7.x the middleware moved; the import raises `ImportError`, which `WalletAdapterFactory` catches and reports as "web3 is required for blockchain operations". All Ethereum-family adapters are therefore unusable.

**Fix**:

- Use the Web3 7.x path: `from web3.middleware.geth_poa import geth_poa_middleware`.
- Pin `web3 >=7.0` in `pyproject.toml` if 6.x support is not required.
- Verify `WalletAdapterFactory.create_adapter('ethereum')` succeeds.

**Verification**:

```bash
cd /opt/aitbc && ./venv/bin/python -c "from aitbc.network.web3_utils import create_web3_client; print('ok')"
```

---

#### A2: Reconcile `SQLModel.metadata` with the Alembic migration graph

**Problem**: `alembic check` reported hundreds of missing tables/indexes relative to `SQLModel.metadata`. The coordinator called `metadata.create_all()` on startup, which could create unmanaged schema objects.

**Fix**:

- Stop unconditional `SQLModel.metadata.create_all()` on startup in `storage/db.py` and `init_async_db`; schema is managed by Alembic `upgrade head`.
- Add `alembic/script.py.mako` so autogenerate can find the template.
- Fix domain model `sa_column` declarations so `Numeric(20, 8)` monetary columns with `Decimal` defaults are `nullable=False`, matching the existing migration graph.
- Generate `alembic/versions/021f508dbce7_reconcile_schema.py` to drop stale tables (`regional_council`, `regional_proposal`, `staking_pool`, `staking_position`, `settlements`) and stale indexes left by earlier migrations.
- Update `tests/unit/test_v0519_tech_debt.py` to assert the new head revision and run `alembic check`.

**Verification**:

```bash
cd /opt/aitbc/apps/coordinator-api
PYTHONPATH=src DATABASE_URL=sqlite:///tmp/alembic_check.db ../../venv/bin/python -m alembic upgrade head
PYTHONPATH=src DATABASE_URL=sqlite:///tmp/alembic_check.db ../../venv/bin/python -m alembic check
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit/test_v0519_tech_debt.py -q
```

---

#### A3: Fix async database URL conversion

**Problem**: `database_async.py` `_build_async_url()` splits URLs on `?`, corrupting query strings like `sqlite:///foo.db?mode=ro` and `postgresql://...?sslmode=require`.

**Fix**:

- Parse URLs with `urllib.parse` instead of string slicing.
- Preserve query parameters after the async driver suffix.
- Reject unsupported schemes instead of appending `+aiosqlite`.

**Verification**:

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts="" -k database_async
```

---

## Agent B — Infrastructure & Apps

**Scope**: All security and correctness issues in `apps/`, `scripts/`, `cli/`, and test/CI configuration.

**Working directory**: `/opt/aitbc/`

**Verification commands**:

```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/ cli/ scripts/ tests/
cd /opt/aitbc/apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
cd /opt/aitbc && ./venv/bin/python -m pytest tests/cli -q -o addopts=""
cd /opt/aitbc && ./venv/bin/python -m pytest tests/security -q -o addopts=""
```

### Tasks — Agent B — Infrastructure & Apps

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Credential hygiene in scripts | 🔴 P0 | `scripts/utils/workspace-manager.sh`, `scripts/utils/claim-task.py`, `scripts/monitoring/monitor-prs.py` | ✅ |
| B2 | Install `AuthMiddleware` and protect financial/admin routes | 🔴 P0 | `apps/coordinator-api/src/coordinator_api/main.py`, `aitbc/auth/middleware.py`, `apps/coordinator-api/src/coordinator_api/contexts/*/routers/oracle.py`, `cross_chain_integration.py`, `marketplace_gpu.py`, `admin.py` | ✅ |
| B3 | Require signatures on marketplace transactions | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py`, `apps/blockchain-node/src/aitbc_chain/rpc/utils.py`, `apps/blockchain-node/src/aitbc_chain/state/state_transition.py` | ✅ |
| B4 | Fix fake marketplace payment paths | 🔴 P0 | `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py` | ✅ |
| B5 | Fix wallet adapters | 🔴 P0 | `apps/coordinator-api/src/coordinator_api/agent_identity/wallet_adapter_enhanced.py` | ✅ |
| B6 | Replace or disable insecure FHE | 🔴 P0 | `apps/coordinator-api/src/coordinator_api/contexts/zk_applications/services/fhe_enhanced.py`, `apps/coordinator-api/src/coordinator_api/contexts/zk_applications/routers/fhe.py` | ✅ |
| B7 | Verify audit authorization token signatures | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/contexts/security/services/key_management.py` | ✅ |
| B8 | Restrict file permissions for keys and DBs | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/contexts/security/services/key_management.py`, `apps/coordinator-api/src/coordinator_api/contexts/confidential/routers/confidential.py`, `apps/blockchain-node/src/aitbc_chain/database.py` | ✅ |
| B9 | Fix staking anonymous auth fallback | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py` | ✅ |
| B10 | Fix multi-tenant quota models | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/models/multitenant.py`, `apps/coordinator-api/src/coordinator_api/contexts/security/services/quota_enforcement.py` | ✅ |
| B11 | Fix governance state persistence | 🟡 P1 | `apps/coordinator-api/src/coordinator_api/contexts/governance/services/governance_service.py`, `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/governance_enhanced.py` | ✅ |
| B12 | Expand CI/test path coverage | 🟡 P1 | `pyproject.toml`, `.github/workflows/ci.yml`, `.gitea/workflows/*` | ✅ |
| B13 | Remove duplicate broken CLI setup | 🟡 P1 | `cli/setup/setup.py` | ✅ |
| B14 | Fix `validate_query()` case-sensitivity | 🟡 P1 | `apps/blockchain-node/tests/security/test_database_security.py` | ✅ |

### Agent B — Detailed Instructions

#### B1: Credential hygiene in scripts

Remove hardcoded `GITEA_TOKEN` fallbacks and `curl -k`/`verify=False` from `scripts/utils/workspace-manager.sh`, `scripts/utils/claim-task.py`, and `scripts/monitoring/monitor-prs.py`. Read tokens from environment or file and fail closed. Rotate all exposed credentials outside the repo.

**Verification**:

```bash
cd /opt/aitbc && grep -R "GITEA_TOKEN\|verify=False\|--insecure\|curl -k" scripts/ --include="*.sh" --include="*.py" | wc -l
# Expected: 0
```

#### B2: Install `AuthMiddleware` and protect financial/admin routes

Add `AuthMiddleware` to `apps/coordinator-api/src/coordinator_api/main.py` (or add FastAPI auth dependencies) for oracle price setting, cross-chain signing/whitelist, GPU sale/booking/release/confirm/delete, and admin settings. Mark genuinely public routes with a `ponytail:` comment.

**Verification**: Unauthorized requests return 401/403; `Depends(get_current_user)`/`Depends(get_current_address)` covers the protected routes.

#### B3: Require signatures on marketplace transactions

In `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py`, verify the sender signature before state application. In `rpc/utils.py`, do not strip the signature. In `state/state_transition.py`, verify ownership if not already verified.

**Verification**: Unsigned marketplace transactions are rejected; signed valid transactions pass. Add regression tests.

#### B4: Fix fake marketplace payment paths

Make `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py` `/payments/send` record or submit a real payment and return failure when payment fails. The GPU purchase flow must roll back booking on payment failure and not return `purchased` on a failed payment.

**Verification**: Unit tests for failed payment return 402/failure and no `purchased` status.

#### B5: Fix wallet adapters

In `apps/coordinator-api/src/coordinator_api/agent_identity/wallet_adapter_enhanced.py`, verify AITBC signatures against the public key and message, not just a hex regex. For the Ethereum adapter, pass the private key to `Account.from_key`, not `from_address`.

**Verification**: Sign/verify with valid keys works; invalid signatures are rejected; Ethereum adapter initializes without error.

#### B6: Replace or disable insecure FHE

The `fhe_enhanced.py` BFV implementation is not cryptographically secure. Either replace it with a vetted FHE library or make the service raise `NotImplementedError`/return 501 and add an auth dependency to `fhe.py` routes.

**Verification**: Existing tests do not expose fake encryption as secure; unauthenticated requests are rejected if auth is enabled.

#### B7: Verify audit authorization token signatures

Sign audit tokens with a service key and verify HMAC/ECDSA in `apps/coordinator-api/src/coordinator_api/contexts/security/services/key_management.py`. Remove the `"placeholder"` signature and base64-only validation.

**Verification**: Forged tokens are rejected; valid tokens are accepted; tests added.

#### B8: Restrict file permissions for keys and DBs

- `FileKeyStorage` writes `.priv` files with mode `0o600` and sets the key directory to `0o700`.
- `confidential.py` uses a configurable secure directory (not `/tmp`) with restricted permissions.
- `apps/blockchain-node/src/aitbc_chain/database.py` no longer chmods DB/WAL files to `666`; use `0o640` or leave the default.

**Verification**: Reproduction script confirms `0o600` private keys, no world-readable DB files.

#### B9: Fix staking anonymous auth fallback

Change `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py` optional auth to require a valid token. Remove the `test_user_address` fallback.

**Verification**: Missing token returns 401; valid token uses the real staker address.

#### B10: Fix multi-tenant quota models

Add `table=True` to `apps/coordinator-api/src/coordinator_api/models/multitenant.py` models and pass `job_id` when constructing `UsageRecord` in `quota_enforcement.py`.

**Verification**: `select(TenantQuota)` works; quota service tests pass.

#### B11: Fix governance state persistence

Persist councils/proposals in the database in `apps/coordinator-api/src/coordinator_api/contexts/governance/services/governance_service.py` instead of in-memory service instances. Use a scoped dependency or singleton service backed by DB.

**Verification**: Create a council in one request, list in another, and the council is returned.

#### B12: Expand CI/test path coverage

Add `tests/cli`, `tests/security`, `tests/services`, `tests/production`, and `apps/blockchain-node/tests` to `pyproject.toml` `testpaths` and CI workflows. Fix or quarantine pre-existing failures; do not lower gates.

**Verification**: CI runs all configured suites and fails on unexpected skips.

#### B13: Remove duplicate broken CLI setup

Either delete `cli/setup/setup.py` or fix its version and entry point to match `cli/setup.py`. Only one installable CLI setup path should remain.

**Verification**: `pip install -e cli/` works and `aitbc --version` reports the correct version.

#### B14: Fix `validate_query()` case-sensitivity

In `apps/blockchain-node/tests/security/test_database_security.py`, update `validate_query()` to compare the lowercased query against lowercase patterns. Remove the `xfail` if the test now passes.

**Verification**: `DELETE FROM account` and `UPDATE account SET ...` are rejected.

---

## Coordination

### Shared files / boundaries

- `SQLModel.metadata` and Alembic versions: Agent A and B coordinate. Agent A first proposes shared-core metadata registration changes; Agent B handles coordinator-api models/migrations.
- `aitbc/auth/middleware.py` is shared; Agent A owns type annotations, Agent B owns integration into `apps/coordinator-api/src/coordinator_api/main.py`.

### Coordination Log

| Date | Agent | Request | Status |
|------|-------|---------|--------|
| 2026-07-14 | — | Release plan created; no file locks yet | planned |

---

## Completion Summary

Pending implementation. Acceptance criteria:

- [ ] No hardcoded secrets in tracked files.
- [ ] `AuthMiddleware` installed and all P0 routes require authentication.
- [ ] Marketplace transaction signature verified before state transition.
- [ ] Payment endpoints no longer fake success.
- [ ] Wallet/FHE/audit token signatures cryptographically verified or disabled.
- [ ] Private key and DB files created with owner-only permissions.
- [ ] Web3 7.x import works and Ethereum adapters initialize.
- [ ] `alembic check` passes on a fresh upgraded database.
- [x] CLI/security/services/production suites run in CI without unexpected skips.
- [x] All version strings consistent and `v0.10.13` tag applied after verification.
