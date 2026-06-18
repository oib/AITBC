# AITBC v0.4.26 — Agent A Plan

## Agent: Security, Data & API Integrity

**Scope**: Production safety, runtime correctness, auth hardening, data-layer integrity, API contract enforcement, and test reliability.

**Out of scope**: Monolithic module splits, tooling cleanup, systemd hardening, observability stack consolidation, shell scripts, dependency lockfile management (owned by Agent B).

---

## Assigned Goals

### Goal 1: Make CI Enforce Reality (P0)

**Problem**: `.github/workflows/ci.yml` has `continue-on-error: true` on lint, format, typecheck, and test jobs. Security scans use `|| true`.

**Approach**:
1. Remove `continue-on-error: true` from ruff check and unit tests.
2. Fix the 18 existing Ruff issues.
3. Remove `|| true` from security scan commands.
4. Ensure CI installs the project, not just standalone tools.

---

### Goal 2: Fix Production Auth / Config Safety (P0)

**Problem**: `deps.py` bypasses API-key validation when `APP_ENV=dev`. `settings.environment` is the canonical field but is not used everywhere.

**Approach**:
1. Unify all environment checks to use `settings.environment`.
2. Make auth fail closed.
3. Add `settings.validate_secrets()` call in `main.py` startup.
4. Audit all apps for the same bypass pattern.

---

### Goal 3: Remove and Rotate Tracked Key Material (P0)

**Problem**: `dev/validator_keys.json` contains a full PEM private key committed to the repo.

**Approach**:
1. Delete `dev/validator_keys.json`.
2. Replace with `scripts/generate_dev_keys.py` fixture generator.
3. Add secret scanning to CI.
4. Rotate derived keys.
5. Add `*.pem`, `*private_key*` to `.gitignore`.

---

### Goal 4: Fix Blockchain Loop-Variable Capture Bug (P0)

**Problem**: Ruff B023 found 4 instances in `aitbc_chain/main.py` where lambda captures `chain_id` by reference.

**Approach**:
1. Bind loop variables at lambda creation: `lambda chain_id=chain_id: session_scope(chain_id)`.
2. Or refactor to factory functions.
3. Enable Ruff B023 in CI.

---

### Goal 5: Fix SQLModel Metadata Duplication (P1)

**Problem**: `CrossChainMapping` sets `__table_args__` twice, overwriting `extend_existing`.

**Approach**:
1. Merge all `__table_args__` into a single assignment per class.
2. Clean up commented-out `Index` definitions.
3. Audit other SQLModel classes in the same file.

---

### Goal 6: Reconcile Tests with Implementation (P1)

**Problem**: `tests/unit` expects security headers that `middleware.py` does not provide.

**Approach**:
1. Add security-header middleware or adjust tests.
2. Fix pytest `addopts` coverage drift.

---

### Goal 7: Make Type Checking Honest and Incremental (P1)

**Problem**: mypy `exclude` list has ~90 regexes; 411 errors in 44 files are ignored by CI.

**Approach**:
1. Generate mypy baseline.
2. Enforce "no new errors" on changed files.
3. Shrink exclude list deliberately.

---

### Goal 15: Replace Fallback Secrets and Hardcoded Test Keys (P0)

**Problem**: `default-secret-key-change-in-production`, `"changeme"`, `"test-key"` are active defaults.

**Approach**:
1. Raise `RuntimeError` if `JWT_SECRET_KEY` is missing.
2. Make `coordinator_shared_secret` required.
3. Remove unconditional `"test-key"` return from `auth.py`.
4. Audit repo for weak default strings.

---

### Goal 22: Use Timezone-Aware Timestamps (P1)

**Problem**: Naive `datetime.now()` in `caching.py`, `feature_flags.py`, `monitoring.py`.

**Approach**:
1. Bulk-replace with `datetime.now(UTC)`.
2. Add lint rule to prevent naive `now()`.

---

### Goal 23: Add Lifecycle Management for Async Tasks (P1)

**Problem**: Bare `asyncio.create_task()` with no cancellation or error logging.

**Approach**:
1. Create `TaskRegistry` in `aitbc/async_tasks.py`.
2. Cancel tracked tasks on shutdown.
3. Log unhandled exceptions.

---

### Goal 24: Consolidate Coordinator DB Setup (P1)

**Problem**: Four overlapping DB modules: `database.py`, `storage/db.py`, `database_async.py`, `storage/db_pg.py`.

**Approach**:
1. Pick one canonical boundary.
2. Deprecate others with aliases.
3. Move `create_all()` out of startup.

---

### Goal 25: Replace Float Money Fields with Decimal (P0)

**Problem**: `float` for amounts in `cross_chain_bridge.py`, `bounty.py`, `rewards.py`.

**Approach**:
1. Replace with `Decimal`.
2. Add regression test for token math.
3. Audit all `float` fields for financial use.

---

### Goal 26: Fix Mutable Defaults in Models (P1)

**Problem**: `default={}` and `default=[]` in Pydantic/SQLModel classes.

**Approach**:
1. Replace with `default_factory=dict` / `default_factory=list`.
2. Add pre-commit check.

---

### Goal 27: Stop Returning Internal Exception Details from 500s (P0)

**Problem**: `str(exc)` leaked to clients in `main.py` and RPC errors.

**Approach**:
1. Replace with opaque error codes.
2. Log full details server-side.
3. Add sanitizing middleware.

---

### Goal 28: Audit Blocking Calls in Async Services (P1)

**Problem**: `requests.get()` and `time.sleep()` inside async paths.

**Approach**:
1. Replace with `httpx.AsyncClient` and `asyncio.sleep()`.
2. Add lint check.

---

### Goal 29: Migrate Pydantic v1 Config to v2 ConfigDict (P2)

**Problem**: `class Config:` deprecation warnings.

**Approach**:
1. Replace with `model_config = ConfigDict(...)`.
2. Run tests to verify behavior.

---

### Goal 30: Fix Duplicate SQLModel Metadata (P1)

**Problem**: Global `app` import at test time populates metadata.

**Approach**:
1. Enforce `create_app()` fixtures.
2. Add startup assertion for duplicate tables.

---

### Goal 32: Add Duplicate-Route Guard (P0)

**Problem**: Duplicate method/path registrations from repeated `include_router` calls.

**Approach**:
1. Build startup guard that fails on duplicate `(method, path)`.
2. Coordinate with Agent B (Goal 12) for deduplication.

---

### Goal 35: Strengthen API Contract Validation (P1)

**Problem**: Only 338 of 861 routes have `response_model=`.

**Approach**:
1. Require `response_model=` on all public endpoints.
2. Add CI lint check.

---

### Goal 36: Normalize Auth (P0)

**Problem**: Blockchain RPC uses `X-Wallet-Address` only; coordinator has unauthenticated routes.

**Approach**:
1. Create `RouteSecurityMatrix`.
2. Apply in middleware.
3. Add JWT support to RPC.

---

### Goal 37: Clean Up Versioned Path Prefixes (P1)

**Problem**: Double-prefix paths like `/v1/api/v1/dashboard`.

**Approach**:
1. Remove embedded version prefixes from router modules.
2. Add assertion for `/v1/v1/`.

---

### Goal 38: Make CORS Production Assertions Testable (P1)

**Problem**: No assertion against wildcard + credentials in production.

**Approach**:
1. Add startup assertion in `create_app()`.
2. Add unit test.

---

### Goal 39: Fail Closed for Mock Crypto Paths (P1)

**Problem**: Mock contract addresses, ciphertext, signatures in production routes.

**Approach**:
1. Gate behind `settings.debug` or `ENABLE_MOCK_CRYPTO`.
2. Add CI grep check.

---

### Goal 40: Replace Hardcoded Mock RPC/Private Key Paths (P0)

**Problem**: `"mock_rpc_url"` and `"mock_private_key"` as active defaults.

**Approach**:
1. Make fields required, raise `RuntimeError` if missing.
2. Move test fixtures to `tests/`.

---

### Goal 41: Add OpenAPI CI Check (P1)

**Problem**: No automated validation of generated OpenAPI spec.

**Approach**:
1. Validate `openapi.json` in CI for duplicates, auth, mock routes, missing schemas.
2. Fail build on violation.

---

## Cross-Agent Dependencies

| Agent B Task | Why Agent A Depends | Coordination Point |
|--------------|---------------------|-------------------|
| Goal 12: Deduplicate router registration | Guard (Goal 32) fails until duplicates removed | Agent B completes deduplication first |
| Goal 13: Disable docs in production | CORS assertions may need to account for disabled docs | Share `create_app()` changes |
| Goal 14: Replace broad `except Exception` | Auth normalization may add imports needing explicit handling | Coordinate on `main.py` imports |
| Goal 33: Mock router flags | Mock crypto gating should use same flag pattern | Agree on shared flag convention |
| Goal 45: Harden systemd units | Secret removal and 500 sanitization affect logging | Ensure 500s still log through journal |

---

## Phase Breakdown

### Phase 1: Safety & Enforcement (Week 1)

| Day | Task | Verification | Priority |
|-----|------|--------------|----------|
| 1-2 | Fix CI `continue-on-error`; fix 18 Ruff issues | CI lint job passes | P0 |
| 2-3 | Fix B023 blockchain loop capture | Ruff B023 clean | P0 |
| 2-3 | Unify auth; remove `APP_ENV=dev` bypass | Auth tests pass in production mode | P0 |
| 3-4 | Delete `dev/validator_keys.json`; add generator | Zero tracked PEM keys | P0 |
| 3-4 | Add secret scanning to CI | CI blocks on committed secrets | P0 |
| 4-5 | Call `validate_secrets()` at startup | Missing secrets raise at boot | P0 |
| 4-5 | Replace fallback secrets | Bandit B105 clean | P0 |
| 4-5 | Replace float money with `Decimal` | No `float` for token amounts | P0 |
| 5 | Sanitize 500 responses | Opaque error codes only | P0 |
| 5 | Replace mock RPC/key paths | No `"mock_*"` literals | P0 |
| 5 | Normalize auth across services | Route security matrix covers all `/v1/*` | P0 |

### Phase 2: Data Layer & Runtime (Week 2)

| Day | Task | Verification | Priority |
|-----|------|--------------|----------|
| 1-2 | Fix SQLModel `__table_args__` duplication | No `Table already defined` | P1 |
| 2-3 | Reconcile tests vs middleware | `pytest tests/unit` passes | P1 |
| 3-4 | Fix pytest `addopts` drift | No argument errors | P1 |
| 3-4 | Isolate test app instances | No metadata conflicts | P1 |
| 4-5 | Consolidate coordinator DB setup | One canonical boundary | P1 |
| 5 | Fix mutable defaults | Custom check catches them | P1 |
| 5 | Timezone-aware timestamps | Zero naive `datetime.now()` | P1 |

### Phase 3: API Integrity & Validation (Week 3)

| Day | Task | Verification | Priority |
|-----|------|--------------|----------|
| 1-2 | Add duplicate-route guard | Zero duplicate (method, path) | P0 |
| 2-3 | Disable docs/redoc/debug in production | 404 in prod, 200 in dev | P1 |
| 3-4 | Add async task lifecycle management | Clean shutdown with registry | P1 |
| 3-4 | Replace MD5 with SHA256 | Bandit B303 clean | P1 |
| 4-5 | Remove blocking calls from async paths | `httpx` and `asyncio.sleep` | P1 |
| 4-5 | Fix duplicate SQLModel metadata | Full suite collects cleanly | P1 |
| 5 | Strengthen API contracts | All public endpoints have `response_model` | P1 |
| 5 | Clean up versioned prefixes | No `/v1/v1/` paths | P1 |
| 5 | CORS production assertions | Test fails on bad config | P1 |
| 5 | Mock crypto paths gated | Disabled in production | P1 |
| 5 | OpenAPI CI check | Validates spec before build passes | P1 |

### Phase 4: Type Checking & Pydantic (Week 4)

| Day | Task | Verification | Priority |
|-----|------|--------------|----------|
| 1-3 | Generate mypy baseline; enforce incremental | New errors block PR | P1 |
| 3-4 | Migrate `class Config:` to `ConfigDict` | Zero deprecation warnings | P2 |
| 4-5 | Shrink mypy exclude list | More modules type-checked | P2 |

---

## Success Criteria

### Minimum Viable
- [ ] Auth fails closed in production
- [ ] No PEM private keys in repo
- [ ] Secret scanning blocks CI
- [ ] `validate_secrets()` at startup
- [ ] SQLModel metadata fixed
- [ ] `tests/unit` passes
- [ ] Mypy enforces incremental
- [ ] No default secrets outside tests
- [ ] MD5 removed from cache keys
- [ ] Float money -> Decimal
- [ ] 500s sanitized
- [ ] Timezone-aware timestamps
- [ ] Mutable defaults fixed
- [ ] DB setup consolidated
- [ ] Blocking calls removed from async paths
- [ ] Duplicate-route guard active
- [ ] All public endpoints have `response_model`
- [ ] Auth normalized (route security matrix)
- [ ] No double-prefix paths
- [ ] CORS assertions testable
- [ ] Mock crypto disabled in production
- [ ] No `"mock_rpc_url"` or `"mock_private_key"` literals
- [ ] OpenAPI CI check passes

### Stretch Goals
- [ ] Full `mypy aitbc/` with 0 errors
- [ ] Full test suite passes
- [ ] Pydantic v1 `Config` fully migrated
- [ ] OpenAPI auto-validated on every PR
- [ ] Route security matrix enforced by middleware

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Auth fix breaks local dev | Medium | Medium | Provide `.env.dev` for unsafe mode |
| `validator_keys.json` deletion breaks scripts | Low | Medium | Generator script replaces it |
| B023 fix changes behavior | Low | High | Multi-chain test before merge |
| Decimal migration breaks serialization | Medium | High | Regression tests for token math |
| 500 sanitization hides debugging | Low | Medium | Server-side logs with tracebacks |
| Async registry crashes on shutdown | Low | Medium | Graceful timeout |
| Timezone timestamps break SQLite | Low | Medium | Test comparisons after migration |
| DB consolidation breaks startup | Medium | High | Integration tests before/after |
| Auth normalization breaks RPC clients | Medium | High | Backward-compatible header during transition |
| Double-prefix cleanup breaks URLs | Medium | Medium | 308 redirects for one cycle |
| Mock crypto removal breaks demos | Low | Low | Move to `examples/` with `debug=True` |
| OpenAPI check flakes | Low | Low | Deterministic startup order |

---

## Dependencies
- Python 3.13.5 (locked)
- `trufflehog` or `detect-secrets`
- `pytest-cov` or remove coverage from `addopts`
- `httpx` for async HTTP migration
- `bandit` >= 1.7.7 for B303 and B105

---

*Generated from v0.4.26 change.log — Last updated: 2026-06-18*
