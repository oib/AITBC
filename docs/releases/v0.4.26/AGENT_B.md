# AITBC v0.4.26 — Agent B Plan

## Agent: Tooling, Architecture & Operations Hardening

**Scope**: Monolithic module splits, tooling cleanup, systemd hardening, observability stack consolidation, shell scripts, dependency lockfile management, and deployment hygiene.

**Out of scope**: Production safety, runtime correctness, auth hardening, data-layer integrity, API contract enforcement, and test reliability (owned by Agent A).

---

## Assigned Goals

### Goal 8: Reduce Dependency / Tooling Drift (P2)

**Problem**: The repo has multiple `pyproject.toml` files (root + `mutants/`), root `requirements*.txt` files, and app-level lockfiles (e.g., `apps/pool-hub/poetry.lock`). CI installs only standalone tools (`ruff`, `mypy`, `pytest`) rather than the project, so imports fail and type checks are incomplete.

**Impact**: Dev environment and CI are not aligned; "works on my machine" syndrome.

**Approach**:
1. Standardize on **one install path**: `pip install -e ".[dev,test]"` from root `pyproject.toml`.
2. Consolidate or remove stale `requirements*.txt` files; move all dev dependencies into `pyproject.toml` `[project.optional-dependencies]`.
3. Remove hardcoded `/opt/aitbc` and `./venv` assumptions in service wrappers and docs where feasible; prefer environment variables.
4. Ensure CI uses the same install command as local development.

---

### Goal 9: Treat `mutants/` as Generated Output (P2)

**Problem**: `mutants/` contains 1,197 tracked files (~71 MB), some as large as 35k lines. If this is mutation-test output, it should not live in the main source tree. It inflates clone times, complicates greps, and creates false positives in code-review diffs.

**Impact**: Repo bloat; confusion about what is source vs generated.

**Approach**:
1. Confirm whether `mutants/` is intentionally source or purely mutation-test artifacts.
2. If generated: move to CI artifacts, `.gitignore` the directory, and remove from history.
3. If partially source (e.g., custom mutation harnesses): extract source files to a dedicated directory and `.gitignore` the generated remainder.
4. Update any scripts that reference `mutants/` to handle the new location.

---

### Goal 10: Break Up Monolithic Modules (P2)

**Problem**: Several hand-written modules exceed 500 lines and mix routing, business logic, and schema definitions:
- `cli/aitbc_cli/commands/market.py` — 1,814 lines
- `cli/aitbc_cli/commands/wallet.py` — 1,583 lines
- `apps/blockchain-node/src/aitbc_chain/rpc/router.py` — 858 lines
- `aitbc/caching.py` — 926 lines

**Impact**: Difficult to test, review, and maintain. No clear separation of concerns.

**Approach**:
1. Split each monolithic file into logical modules (routing, business logic, schemas, utilities).
2. Create subpackages where appropriate (e.g., `cli/aitbc_cli/commands/market/`).
3. Update imports across the codebase.
4. Add `__init__.py` re-exports for backward compatibility during deprecation window.

**Detailed Plan**: See `REFACTORING_PLANS.md` for specific file-by-file breakdown.

---

### Goal 11: Reduce `sys.path` and Hardcoded Path Assumptions (P2)

**Problem**: `sys.path.insert(0, ...)` and hardcoded `/opt/aitbc` appear across wrappers, CLI, scripts, and SDK defaults. This makes the code fragile outside the exact production path and complicates local development.

**Impact**: Brittle deployments; duplicate imports; model registration races when paths are inserted multiple times.

**Approach**:
1. Audit all `sys.path.insert` calls in `aitbc/`, `cli/`, `scripts/`, and `apps/`.
2. Replace with installed package entry points (e.g., `python -m aitbc_cli.commands.market`).
3. Derive `REPO_DIR` from an environment variable (`AITBC_HOME`) with a sensible default, never hardcoded.
4. Update SDK defaults to use environment variables or XDG base directories.

---

### Goal 12: Deduplicate Router Registration in Coordinator (P1)

**Problem**: `apps/coordinator-api/src/app/main.py` registers the same routers multiple times with different prefixes. `agent_router` appears 4 times, `cross_chain` 3 times, `marketplace_offers` 3 times, `portfolio_router` 2 times, `islands_proxy` 3 times, `swarm` 3 times, and `monitor` 3 times.

**Impact**: Duplicate routes cause FastAPI to silently overwrite earlier handlers; requests may reach the wrong endpoint, and OpenAPI documentation becomes inconsistent.

**Approach**:
1. Audit all `include_router` calls in `main.py` (lines 253-420).
2. Remove duplicate registrations; keep only one canonical mount per router.
3. Coordinate with Agent A (Goal 32) to add startup guard after deduplication.

---

### Goal 13: Disable Docs and Debug Routes in Production (P1)

**Problem**: `create_app()` always sets `docs_url="/docs"` and `redoc_url="/redoc"`. A `/_debug/routes` endpoint is registered at module level regardless of environment.

**Impact**: Production deployments expose internal debugging tools and API documentation to unauthorized users.

**Approach**:
1. Gate `docs_url` and `redoc_url` behind `settings.debug` or `settings.environment`.
2. Remove or gate `/_debug/routes` behind a debug flag.
3. Add startup assertion that fails if debug routes are mounted in production.
4. Coordinate with Agent A (Goal 36) for CORS implications.

---

### Goal 14: Replace Broad Optional Router Imports with Feature Flags (P1)

**Problem**: Many router imports are wrapped in `try/except Exception` blocks that swallow import errors and log a warning. This can hide broken modules as "feature unavailable" without surfacing root causes.

**Impact**: Broken modules fail silently; debugging is difficult; false sense of feature availability.

**Approach**:
1. Replace broad `except Exception` with specific `except ImportError`.
2. Add explicit feature flags (e.g., `ENABLE_TRAINING=1`) for optional routers.
3. Log import failures at ERROR level in production, WARNING in dev.
4. Coordinate with Agent A (Goal 36) for auth normalization implications.

---

### Goal 20: Untrack Cached and Generated Files (P2)

**Problem**: `cli/.pytest_cache/` contains 5 tracked files despite `.gitignore` rules for caches. Packaged artifacts like `cli/debian/usr/share/aitbc/dist/aitbc_cli-0.1.0-py3-none-any.whl` are tracked in source control.

**Impact**: Repo bloat; false positives in diffs; cache files committed accidentally.

**Approach**:
1. Remove all tracked files from `.pytest_cache/` directories.
2. Add aggressive `.gitignore` patterns for cache directories.
3. Remove packaged `.whl` files from source control; build them in CI.
4. Add pre-commit hook to prevent future cache commits.

---

### Goal 21: Document Dependency Management Source of Truth (P2)

**Problem**: Root Poetry, app-level Poetry files, root `requirements*.txt`, and `uv.lock` all coexist. It is unclear which file is authoritative for CI, local dev, and production deployments.

**Impact**: Dev and CI may install different dependency trees; security upgrades are applied inconsistently.

**Approach**:
1. Pick one primary lock workflow (proposed: root `pyproject.toml` + `uv.lock`).
2. Document the chosen workflow in `docs/development/DEPENDENCIES.md`.
3. Remove obsolete `requirements*.txt` or generate them from `pyproject.toml` in CI if needed.
4. Ensure CI and local dev both use the same lockfile.

---

### Goal 31: Remove Hardcoded Paths and `sys.path.insert` from Runtime Wrappers (P2)

**Problem**: Hardcoded `/opt/aitbc` and `sys.path.insert(0, ...)` appear in service wrappers and startup scripts. This was partially covered in Goal 11 (general path cleanup), but the runtime wrappers are a specific hotspot.

**Impact**: Brittle deployments; duplicate imports; model registration races when paths are inserted multiple times.

**Approach**:
1. Audit all `sys.path.insert` calls in `apps/*/scripts/`, `scripts/services/`, and wrapper files.
2. Replace with installed package entry points (e.g., `python -m aitbc_chain.main`).
3. Derive `REPO_DIR` from an environment variable (`AITBC_HOME`) with a sensible default, never hardcoded.
4. Document the new pattern in `docs/development/SERVICE_WRAPPERS.md`.

**Overlap note**: This is a focused follow-up to Goal 11 for runtime wrappers specifically.

---

### Goal 33: Move Mock/Prototype Routers Behind Non-Production Flags (P1)

**Problem**: Several routers expose in-memory mock or prototype behavior on production paths:
- `apps/coordinator-api/src/app/routers/training.py:20` — in-memory training jobs
- `apps/coordinator-api/src/app/routers/hermes.py:21` — Hermes message stubs
- `apps/coordinator-api/src/app/contexts/agent_coordination/routers/swarm.py:12` — swarm nodes/tasks stubs
- `apps/blockchain-node/src/aitbc_chain/rpc/contracts_stub.py:8` — contract stubs

**Impact**: Production deployments may accidentally serve mock data, leading to incorrect client behavior and security confusion.

**Approach**:
1. Gate each mock router behind an explicit feature flag (e.g., `ENABLE_MOCK_TRAINING=1`) or mount them only when `settings.debug == True`.
2. Add a startup assertion that fails if any mock route is mounted in a production environment.
3. Document which routes are real vs mock in `docs/api/MOCK_ROUTES.md`.
4. Coordinate with Agent A (Goal 39) for consistent flag patterns.

---

### Goal 34: Replace Module-Global Mock State with Persistent Backing (P1)

**Problem**: Several routes rely on module-global mutable state (`_mock_jobs`, `_mock_agents`, `_mock_nodes`) that is lost on restart and inconsistent across workers:
- `training.py` — `_mock_jobs` dict
- `hermes.py` — `_mock_agents` / `_mock_nodes`
- `swarm.py` — in-memory node registry

**Impact**: State vanishes on deploy, causing job/agent/node records to disappear. Multi-worker deployments see split-brain data.

**Approach**:
1. Replace all `_mock_*` globals with database or Redis-backed storage.
2. If a route is genuinely temporary, move it behind the mock flag from Goal 33 and document that it is not persistent.
3. Add tests that verify state survives an app restart (or, for mock routes, explicitly assert that it does not).

---

### Goal 42: Pick One Dependency Source of Truth (P1)

**Problem**: The repo has root Poetry files, `uv.lock`, app-level `poetry.lock` files, and top-level `requirements*.txt` with looser versions. These are maintained independently and can diverge silently.

**Impact**: CI installs from one file while developers use another; deployments may get different dependency trees; security upgrades are applied inconsistently.

**Approach**:
1. Pick one primary lock workflow (proposed: root `pyproject.toml` + `uv.lock`).
2. Generate all secondary files (`requirements*.txt`, app-level lockfiles) from the primary in CI, never by hand.
3. Add a CI check that fails if any generated lockfile is out of sync with the primary.
4. Document the workflow in `docs/development/DEPENDENCIES.md` (Goal 21).

---

### Goal 43: Align Python/Package Constraints Across Apps (P1)

**Problem**: Apps declare inconsistent Python version constraints:
- Some apps: `^3.13`
- Others: `>=3.13.5,<3.14`
- Root: excludes `3.14.1`

**Impact**: CI and service deploys may resolve to different Python or package versions, causing "works on my machine" failures.

**Approach**:
1. Audit all `pyproject.toml` files for `requires-python` and package version constraints.
2. Standardize on a single constraint string across root and all apps.
3. Add a CI lint check that verifies all `pyproject.toml` files use the same Python version spec.

---

### Goal 44: Remove Docker Claims from Documentation (P2)

**Problem**: Docker docs exist (`docs/governance/09-DEPLOYMENT.md:256`), but AITBC is a Docker-free project. Operators are told to create Docker files manually, which is misleading.

**Impact**: Operators waste time trying to build container images for a platform that deploys exclusively via systemd.

**Approach**:
1. Remove all Docker references from `docs/governance/09-DEPLOYMENT.md` and any other docs.
2. Explicitly document that AITBC deploys via systemd only and does not support Docker or containerization.
3. Add a CI check (or simple grep) that fails if any new `Dockerfile`, `docker-compose.yml`, or Docker references are added to the repo.
4. Update the deployment guide to focus on systemd unit management, service user setup, and environment file configuration.

---

### Goal 45: Harden Systemd Units Consistently (P0)

**Problem**: Several systemd units run as `root` with weak sandboxing:
- `aitbc-agent-daemon.service` — `User=root`, limited security directives
- `aitbc-miner.service` — `User=root`
- `aitbc-agent-management.service` — `User=root`

**Impact**: Compromised services have full root access; sandboxing is inconsistent across the fleet.

**Approach**:
1. Standardize all units on:
   - `NoNewPrivileges=true`
   - `ProtectSystem=strict` (or `full` where needed)
   - `PrivateTmp=true`
   - `ReadWritePaths=` for only the required data directories
   - `CapabilityBoundingSet=` stripped to minimum
   - Dedicated non-root service users (e.g., `aitbc-agent`, `aitbc-miner`)
2. Create service users in `scripts/setup_service_users.sh`.
3. Audit all 21 active service units against a hardened template.
4. Add a CI check that validates systemd units against the template using `systemd-analyze security`.
5. Coordinate with Agent A (Goal 27) to ensure 500 sanitization still logs through journal.

---

### Goal 46: Move Inline Secrets Out of Service Files (P0)

**Problem**: Secrets are embedded directly in `.service` files:
- `aitbc-miner.service:13` — inline `AUTH_TOKEN`
- `aitbc-governance.service:17` — DB password
- `aitbc-blockchain-p2p.service:14` — DB URL with credentials

**Impact**: Secrets are world-readable if the service file is exposed; rotation requires editing unit files and reloading systemd.

**Approach**:
1. Replace inline secrets with `EnvironmentFile=/etc/aitbc/<service>.env` references.
2. Move all secret values to `/etc/aitbc/*.env` files with `chmod 600`.
3. Update setup scripts to generate these env files during installation.
4. Add `.gitignore` and secret-scanning rules for `/etc/aitbc/` patterns.
5. Document secret rotation procedure in `docs/operations/SECRET_ROTATION.md`.

---

### Goal 47: Make Recovery Fail Loudly (P1)

**Problem**: `aitbc-recovery.service` ends with `|| true`, so secret-loading or relinking failures always report success to systemd.

**Impact**: systemd considers the service healthy even when recovery steps failed; operators may not notice a broken node.

**Approach**:
1. Remove `|| true` from the recovery service `ExecStart` command.
2. Ensure each step in the recovery script exits non-zero on failure.
3. Add `OnFailure=` notification to the unit (e.g., email or webhook alert).
4. Add a test that simulates a recovery failure and verifies systemd reports `failed`.

---

### Goal 48: Add ShellCheck/shfmt to CI (P1)

**Problem**: There are many deployment and maintenance shell scripts with unsafe patterns:
- `scripts/service-management/run-local-services.sh:12` — potential unsafe operations
- `scripts/workflow-hermes/01_preflight_setup_hermes.sh:135` — destructive operations like `fuser -k` and `rm -rf`

**Impact**: Shell scripts can corrupt data, kill wrong processes, or fail silently on different environments.

**Approach**:
1. Add `shellcheck` and `shfmt` to CI.
2. Start with the two scripts above; fix all flagged issues (SC20xx warnings, unquoted variables, etc.).
3. Gradually expand to all `.sh` files in `scripts/`.
4. Fail CI on new shell script additions that do not pass ShellCheck.

---

### Goal 49: Add Dry-Run and Confirmation Modes to Destructive Scripts (P1)

**Problem**: Operational scripts delete chain data, keystores, or kill ports without requiring confirmation:
- `fuser -k` in hermes setup
- `rm -rf` in various maintenance scripts

**Impact**: Accidental execution in production can destroy wallets, chain state, or interrupt active services.

**Approach**:
1. Add `--dry-run` mode to all destructive scripts: print what would be deleted/killed without executing.
2. Add `--yes` / `--confirm` flag requirement for production mode; default to interactive confirmation.
3. Prefer `mv` to backup directory over `rm -rf` where feasible.
4. Document the safety pattern in `docs/operations/SCRIPT_SAFETY.md`.

---

### Goal 50: Standardize Observability (P1)

**Problem**: There are multiple competing metric/tracing modules:
- `aitbc/metrics.py`
- `aitbc/monitoring/monitoring.py`
- `aitbc/tracing_opentelemetry.py`
- `aitbc/distributed_tracing.py`

**Impact**: Inconsistent telemetry; some services emit Prometheus metrics, others OpenTelemetry traces, others custom stats. Dashboards and alerts must handle multiple formats.

**Approach**:
1. Pick one observability path (proposed: OpenTelemetry traces + Prometheus metrics via OTLP).
2. Deprecate the other modules with re-export aliases and warnings.
3. Ensure all FastAPI services use the same middleware for trace IDs, request timing, and DB spans.
4. Standardize service labels (`service.name`, `service.version`, `deployment.environment`) across all units.
5. Document the chosen stack in `docs/operations/OBSERVABILITY.md`.

---

### Goal 51: Lock Down Telemetry Bind Addresses (P1)

**Problem**: `otel-collector-config.yaml` binds telemetry endpoints to `0.0.0.0`, exposing metrics/traces to any network interface.

**Impact**: Telemetry data can be scraped by unauthorized actors; potential data exfiltration or service fingerprinting.

**Approach**:
1. Change bind addresses from `0.0.0.0` to `127.0.0.1` for all telemetry endpoints.
2. If remote scraping is required, bind to specific internal network interfaces only.
3. Add firewall rules or network policies to restrict access.
4. Add CI grep check that fails on new `0.0.0.0` bindings in telemetry configs.

---

## Cross-Agent Dependencies

| Agent A Task | Why Agent B Depends | Coordination Point |
|--------------|---------------------|-------------------|
| Goal 12: Deduplicate router registration | Guard (Goal 32) fails until duplicates removed | Agent B completes deduplication first |
| Goal 13: Disable docs in production | CORS assertions may need to account for disabled docs | Share `create_app()` changes |
| Goal 14: Replace broad `except Exception` | Auth normalization may add imports needing explicit handling | Coordinate on `main.py` imports |
| Goal 33: Mock router flags | Mock crypto gating should use same flag pattern | Agree on shared flag convention |
| Goal 45: Harden systemd units | Secret removal and 500 sanitization affect logging | Ensure 500s still log through journal |

---

## Phase Breakdown

### Phase 1: Tooling & Dependency Cleanup (Week 1)

| Day | Task | Verification | Priority |
|-----|------|--------------|----------|
| 1-2 | Consolidate `requirements*.txt` into root `pyproject.toml` extras | One `pip install -e ".[dev,test]"` works | P2 |
| 2-3 | Standardize CI install path; remove tool-only installs | CI installs project before lint/test | P2 |
| 3-4 | Treat `mutants/` as generated output (`.gitignore` or move) | `git ls-files mutants/ | wc -l` == 0 | P2 |
| 4-5 | Untrack `cli/.pytest_cache/` and packaged `.whl` artifacts | No cache or wheel files in git | P2 |
| 5 | Write `docs/development/DEPENDENCIES.md` source-of-truth doc | Dev and CI use same install path | P2 |

### Phase 2: Architecture Refactoring (Week 2)

| Day | Task | Verification | Priority |
|-----|------|--------------|----------|
| 1-2 | Remove hardcoded `/opt/aitbc` paths in wrappers (where feasible) | Service wrappers use env vars | P2 |
| 2-3 | Break up monolithic modules (market.py, wallet.py, router.py, caching.py) | Each module <400 lines | P2 |
| 3-4 | Remove `sys.path.insert` and hardcoded paths from runtime wrappers | Wrappers use env vars or entry points | P2 |
| 4-5 | Deduplicate router registration in coordinator `main.py` | Startup assertion: zero duplicates | P1 |
| 5 | Replace broad `except Exception` around optional routers | ImportErrors logged at INFO | P1 |

### Phase 3: Mock Data & State Management (Week 3)

| Day | Task | Verification | Priority |
|-----|------|--------------|----------|
| 1-2 | Move mock/prototype routers behind non-production flags | Mock routes return 404 in prod | P1 |
| 2-3 | Replace module-global mock state with DB/Redis backing | `_mock_*` use persistent storage | P1 |
| 3-4 | Disable `/docs`, `/redoc`, `/_debug/routes` in production | Prod config returns 404 on docs | P1 |
| 4-5 | Document mock routes in `docs/api/MOCK_ROUTES.md` | All mock routes documented | P1 |

### Phase 4: Dependency & Python Alignment (Week 4)

| Day | Task | Verification | Priority |
|-----|------|--------------|----------|
| 1-2 | Pick one dependency source of truth; generate secondary files | CI check fails if lockfiles out of sync | P1 |
| 2-3 | Align Python/package constraints across all apps | All `pyproject.toml` use identical constraints | P1 |
| 3-4 | Remove Docker claims from docs; add CI check against Docker files | No Docker files in repo; docs state "systemd only" | P2 |
| 4-5 | Standardize observability (one telemetry stack) | Only one metrics/tracing module per service | P1 |
| 5 | Lock down telemetry bind addresses (`0.0.0.0` → `127.0.0.1`) | CI grep for `0.0.0.0` in telemetry fails | P1 |

### Phase 5: Operations Hardening (Week 5)

| Day | Task | Verification | Priority |
|-----|------|--------------|----------|
| 1-2 | Harden systemd units (non-root users, `NoNewPrivileges`, `ProtectSystem`) | `systemd-analyze security` passes for all units | P0 |
| 2-3 | Move inline secrets out of service files into `/etc/aitbc/*.env` | No secrets in `.service` files | P0 |
| 3-4 | Make recovery service fail loudly (remove `|| true`) | Simulated failure → systemd reports `failed` | P1 |
| 4-5 | Add ShellCheck/shfmt to CI; fix flagged scripts | All `.sh` in `scripts/` pass ShellCheck | P1 |
| 5 | Add dry-run and confirmation modes to destructive operational scripts | `fuser -k` and `rm -rf` require `--yes` or `--dry-run` | P1 |

---

## Success Criteria

### Minimum Viable
- [ ] One dependency lockfile is the source of truth
- [ ] Python constraints aligned across all app `pyproject.toml` files
- [ ] `mutants/` moved out of tracked source tree
- [ ] No tracked cache or wheel artifacts
- [ ] Router duplicates eliminated in coordinator `main.py`
- [ ] `/docs`, `/redoc`, `/_debug/routes` disabled in production
- [ ] Optional routers use explicit feature flags
- [ ] Mock routers gated behind non-production flags
- [ ] Module-global mock state replaced with persistent backing
- [ ] No hardcoded `/opt/aitbc` paths in runtime wrappers
- [ ] Monolithic modules split (market.py, wallet.py, router.py, caching.py)
- [ ] Systemd units hardened (non-root, `NoNewPrivileges`, `ProtectSystem`)
- [ ] No inline secrets in `.service` files
- [ ] Recovery service fails loudly (no `|| true`)
- [ ] All shell scripts pass ShellCheck
- [ ] Destructive scripts have `--dry-run` and require `--yes`
- [ ] One observability stack across all services
- [ ] Telemetry bind addresses locked to localhost
- [ ] Docs explicitly state "systemd only"; no Docker references

### Stretch Goals
- [ ] All `requirements*.txt` removed in favor of `pyproject.toml`
- [ ] Zero hardcoded `/opt/aitbc` paths in source code
- [ ] Full test suite collects without SQLModel metadata conflicts
- [ ] `systemd-analyze security` passes for all 21 service units
- [ ] All `.service` files reference only `EnvironmentFile` for secrets
- [ ] OpenTelemetry collector config does not bind `0.0.0.0` without explicit whitelist

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| CI tool consolidation breaks existing workflows | Medium | Low | Test new install path in a feature branch first |
| Moving `mutants/` breaks mutation-test reporting | Low | Low | Update CI artifact upload path; verify dashboard links |
| Disabling docs in production breaks API consumers | Low | Medium | Announce change; provide static OpenAPI JSON export |
| Module split breaks existing imports | Medium | Medium | Keep re-export aliases in old modules during deprecation window |
| Consolidating dependency files breaks app installs | Medium | Medium | Test install path on a fresh VM/container before merging |
| Python constraint alignment breaks older app installs | Low | Low | Ensure minimum is still `>=3.13`; only tighten upper bounds |
| Systemd hardening breaks services that need root access | Medium | High | Audit each service's actual FS needs; use `ReadWritePaths=` granularly |
| Moving secrets to env files breaks existing deployments | Medium | High | Provide migration script; document env file setup |
| Recovery service loud failure causes false alerts | Low | Medium | Tune alert thresholds; add retry logic for transient failures |
| ShellCheck fixes break script behavior | Medium | Medium | Test scripts in staging before production deployment |
| Dry-run mode adds complexity to script logic | Low | Low | Keep dry-run implementation simple; add tests |
| Observability consolidation breaks existing dashboards | Medium | High | Run new stack in parallel before cutover; update all dashboards |
| Telemetry bind lockdown breaks remote monitoring | Low | Medium | Document internal network requirements; provide VPN access |

---

## Dependencies
- Python 3.13.5 (locked)
- `shellcheck` and `shfmt` for CI
- `systemd-analyze` for unit validation
- `uv` for lockfile management (if chosen as source of truth)
- OpenTelemetry collector and Prometheus (if chosen as observability stack)

---

*Generated from v0.4.26 change.log and REFACTORING_PLANS.md — Last updated: 2026-06-18*
