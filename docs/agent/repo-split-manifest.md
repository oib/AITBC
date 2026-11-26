# Repo split manifest — scripts/ classification

Source issue: #2958 (REPO-SPLIT-CLASSIFY-1), parent epic #2956. Static analysis only; no live fleet probing.
Base commit: `ae618255e9`. Generated inventory count: **420 tracked path entries under `scripts/` (419 regular files + 1 symlink); 420 manifest lines**.

## Classification key

- **PRODUCT** — public `aitbc` repo: needed by a stranger operating a node/island, or referenced from product runtime/tests/hooks in a way that must remain available.
- **OPS** — private `aitbc-ops` repo: fleet monitoring, incident/forensics, failover, multi-host deployment, production stress/chaos, internal mirroring and agent-workflow machinery.
- **DEV-INFRA** — product-side engineering gates/generators invoked by hooks, CI, release, docs, packaging, or test development; tagged distinctly because hook survival depends on it.
- **LEAK** — file content contains the operator domain or internal fleet address prefixes and therefore enters the scrub pass regardless of class.
- **XB->OPS** / **XB->PRODUCT-SIDE** — the file statically references scripts across the OPS vs PRODUCT-side boundary; these are carve-out break-points. PRODUCT and DEV-INFRA are the same side because both stay public.

## Counts by top-level directory

| directory | PRODUCT | OPS | DEV-INFRA | total |
|---|---:|---:|---:|---:|
| `(root)` | 3 | 0 | 8 | 11 |
| `agent` | 1 | 0 | 0 | 1 |
| `audit` | 0 | 1 | 0 | 1 |
| `ci` | 0 | 0 | 43 | 43 |
| `config` | 1 | 0 | 0 | 1 |
| `deployment` | 11 | 16 | 0 | 27 |
| `dev` | 0 | 0 | 4 | 4 |
| `development` | 0 | 0 | 4 | 4 |
| `docs` | 0 | 0 | 13 | 13 |
| `gpu` | 1 | 0 | 0 | 1 |
| `lint` | 0 | 0 | 4 | 4 |
| `maintenance` | 5 | 0 | 0 | 5 |
| `migration` | 4 | 0 | 0 | 4 |
| `monitoring` | 1 | 81 | 0 | 82 |
| `notifications` | 0 | 0 | 1 | 1 |
| `ops` | 14 | 51 | 5 | 70 |
| `performance` | 0 | 0 | 1 | 1 |
| `quality` | 0 | 0 | 1 | 1 |
| `release` | 0 | 0 | 2 | 2 |
| `reset-harness` | 0 | 4 | 0 | 4 |
| `security` | 3 | 2 | 4 | 9 |
| `service-management` | 0 | 6 | 0 | 6 |
| `services` | 2 | 0 | 3 | 5 |
| `setup` | 2 | 0 | 0 | 2 |
| `stress` | 0 | 32 | 0 | 32 |
| `sync` | 0 | 1 | 0 | 1 |
| `templates` | 0 | 0 | 1 | 1 |
| `testing` | 6 | 8 | 2 | 16 |
| `utils` | 19 | 14 | 6 | 39 |
| `workflow` | 0 | 28 | 0 | 28 |
| `zk` | 0 | 0 | 1 | 1 |
| **total** | **73** | **244** | **103** | **420** |

## Per-file manifest

- `scripts/README.md` — **PRODUCT** — refs: test: tests/README.md, tests/unit/test_v2399_health_gate_paths.py; doc: docs/README.md
- `scripts/agent/register-agent.sh` — **PRODUCT** — refs: no exact static refs
- `scripts/aitbc-cli` — **PRODUCT** — refs: app/cli/pkg: cli/tests/test_cli_basic.py, cli/tests/test_cli_comprehensive.py; test: cli/tests/test_cli_basic.py, cli/tests/test_cli_comprehensive.py; doc: 9 refs incl. docs/archive/development/CLI_PACKAGING_PLAN.md, docs/cli/testing.md
- `scripts/aitbc-miner` — **PRODUCT** — tracked absolute-symlink convenience launcher for miner CLI; dangling in a clean clone — repair or delete in carve-out, not fleet OPS; refs: no exact static refs
- `scripts/audit/reconcile_agent_wallets.py` — **OPS** — refs: doc: docs/releases/2026/versions/v0.12/v0.12.0_AGENTS.md
- `scripts/check-production-readiness.py` — **DEV-INFRA** — release/deploy readiness gate; Makefile/test references; refs: test: tests/unit/test_deploy_migrations.py; doc: 4 refs incl. docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334; other: Makefile
- `scripts/check_no_assert_print.py` — **DEV-INFRA** — pre-commit assert/print ratchet; refs: hook: .pre-commit-config.yaml; test: tests/unit/test_check_no_assert_print.py; doc: docs/releases/2026/versions/v0.10/v0.10.12_AGENTS.md, docs/releases/2026/README.md#v01012, docs/releases/2026/versions/v0.10/v0.10.16_AGENTS.md
- `scripts/ci/assert-print-baseline.txt` — **DEV-INFRA** — refs: test: tests/unit/test_check_no_assert_print.py
- `scripts/ci/c901-baseline.txt` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; script: scripts/ci/check-c901-ratchet.sh, scripts/ci/render-c901-watch-list.py; other: Makefile, pyproject.toml
- `scripts/ci/c901-watch-list.md` — **DEV-INFRA** — refs: test: tests/ci/test_render_c901_watch_list.py; script: scripts/ci/render-c901-watch-list.py; doc: docs/ci-cd/README.md
- `scripts/ci/check-bandit.sh` — **DEV-INFRA** — refs: other: Makefile
- `scripts/ci/check-c901-ratchet.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; script: 4 refs incl. scripts/ci/c901-watch-list.md, scripts/ci/check-except-ratchet.sh; other: Makefile, pyproject.toml
- `scripts/ci/check-cli-docs.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; ci: .gitea/workflows/ci.yml, .github/workflows/ci.yml; script: scripts/ci/run-suite-manual.sh
- `scripts/ci/check-coverage-ratchet.sh` — **DEV-INFRA** — refs: script: scripts/ci/coverage-baseline.txt, scripts/ci/run-suite-manual.sh; other: Makefile, pyproject.toml
- `scripts/ci/check-critical-path-tests.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; script: scripts/ci/critical-paths.txt, scripts/ci/run-suite-manual.sh; other: Makefile
- `scripts/ci/check-env-matches-lock.py` — **DEV-INFRA** — refs: script: scripts/ci/run-suite-manual.sh; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02310
- `scripts/ci/check-except-ratchet.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; test: tests/ci/test_except_ratchet_scans.py; script: scripts/ci/c901-watch-list.md, scripts/ci/render-c901-watch-list.py, scripts/ci/run-suite-manual.sh; doc: docs/releases/2026/README.md#v0257; other: Makefile
- `scripts/ci/check-fake-async.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml
- `scripts/ci/check-mcp-cli-drift.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; script: scripts/dev/generate_mcp_cli_tools.py; doc: docs/releases/2026/README.md#v02513
- `scripts/ci/check-mcp-tool-surface.py` — **DEV-INFRA** — refs: script: scripts/ci/check-mcp-cli-drift.sh, scripts/dev/gen_mcp_tool_inventory.py
- `scripts/ci/check-merge-markers.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02312
- `scripts/ci/check-module-size.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; script: scripts/ci/run-suite-manual.sh; other: Makefile
- `scripts/ci/check-openapi-drift.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; test: tests/unit/test_openapi_drift_guard.py; script: scripts/ci/run-suite-manual.sh; other: Makefile
- `scripts/ci/check-package-managers.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml
- `scripts/ci/check-shell-strict-mode.py` — **DEV-INFRA** — XB->OPS scripts/service-management/lib/services.sh, scripts/utils/env_config.sh; refs: hook: .pre-commit-config.yaml; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02312
- `scripts/ci/check-type-ignores.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; doc: docs/releases/2026/versions/v0.10/v0.10.16_AGENTS.md, docs/releases/2026/README.md#v01016
- `scripts/ci/check-unawaited-async.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; test: tests/ci/test_check_unawaited_async.py; script: scripts/ci/run-suite-manual.sh
- `scripts/ci/check-version-consistency.py` — **DEV-INFRA** — refs: app/cli/pkg: cli/tests/test_version.py; test: cli/tests/test_version.py; script: scripts/ci/run-suite-manual.sh; doc: docs/releases/README.md; other: Makefile
- `scripts/ci/check-website-stamp.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml
- `scripts/ci/check-zk-circuit-sync.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; app/cli/pkg: apps/coordinator-api/src/coordinator_api/contexts/zk_applications/services/zk_proofs.py; doc: docs/archive/security/audit-findings.md, docs/releases/2026/README.md#v0259
- `scripts/ci/check_deprecation_cleanup.sh` — **DEV-INFRA** — refs: script: scripts/ci/run-suite-manual.sh; doc: docs/releases/2026/versions/v0.11/v0.11.0_AGENTS.md, docs/web/README.md
- `scripts/ci/check_phase4_gates.py` — **DEV-INFRA** — refs: doc: docs/releases/2026/versions/v0.11/v0.11.0_AGENTS.md, docs/releases/2026/README.md#v0110, docs/releases/2026/versions/v0.11/v0.11.0_phase4_gates.yml
- `scripts/ci/check_test_suite_parity.py` — **DEV-INFRA** — refs: script: scripts/ci/run-suite-manual.sh, scripts/ci/test_suites.py; other: Makefile
- `scripts/ci/coverage-baseline.txt` — **DEV-INFRA** — refs: script: scripts/ci/check-coverage-ratchet.sh, scripts/ci/run-suite-manual.sh; other: Makefile, pyproject.toml
- `scripts/ci/critical-paths.txt` — **DEV-INFRA** — refs: script: scripts/ci/check-critical-path-tests.sh; other: Makefile
- `scripts/ci/except-baseline.txt` — **DEV-INFRA** — refs: script: scripts/ci/check-except-ratchet.sh, scripts/ci/render-c901-watch-list.py; other: Makefile
- `scripts/ci/export-requirements.sh` — **DEV-INFRA** — refs: test: tests/test_requirements_tiers.py; doc: docs/deployment/fleet-roles.md, docs/releases/2026/README.md#v0280; other: requirements-dev.txt, requirements.txt
- `scripts/ci/live-scenario-dry-run.sh` — **DEV-INFRA** — refs: script: scripts/ci/run-suite-manual.sh; other: Makefile
- `scripts/ci/manual-ci-known-red.txt` — **DEV-INFRA** — XB->OPS scripts/ops/bridge-leaf-audit.py, scripts/ops/escrow-stuck-sweep.py, scripts/ops/ops_http.py, scripts/ops/post-cut-verify.py, scripts/ops/post_activation_audit.py, scripts/ops/unpause-precheck.py, scripts/reset-harness/gossip_filter.py, scripts/reset-harness/rehearsal.py; refs: script: scripts/ci/run-suite-manual.sh
- `scripts/ci/module-size-baseline.txt` — **DEV-INFRA** — XB->OPS scripts/reset-harness/rehearsal.py; refs: hook: .pre-commit-config.yaml; script: scripts/ci/check-module-size.py; other: Makefile
- `scripts/ci/mypy-baseline.txt` — **DEV-INFRA** — refs: script: scripts/ci/check-c901-ratchet.sh, scripts/ci/mypy-precommit.sh; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02322
- `scripts/ci/mypy-precommit.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; script: scripts/ci/run-suite-manual.sh, scripts/dev/setup.sh; doc: 5 refs incl. docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02322; other: Makefile
- `scripts/ci/render-c901-watch-list.py` — **DEV-INFRA** — refs: test: tests/ci/test_render_c901_watch_list.py; script: scripts/ci/c901-watch-list.md; doc: docs/ci-cd/README.md
- `scripts/ci/repo-python.sh` — **DEV-INFRA** — refs: test: tests/unit/test_repo_python.py; script: scripts/ci/render-c901-watch-list.py; doc: docs/releases/2026/README.md#v02511
- `scripts/ci/run-suite-manual.sh` — **DEV-INFRA** — refs: script: scripts/ci/manual-ci-known-red.txt; LEAK(operator-domain)
- `scripts/ci/setup-job-logging.sh` — **DEV-INFRA** — refs: script: scripts/ci/check_deprecation_cleanup.sh
- `scripts/ci/setup-python-venv.sh` — **DEV-INFRA** — refs: ci: .gitea/workflows/ci.yml, .gitea/workflows/nightly.yml; test: tests/unit/test_setup_python_venv.py; script: scripts/ci/mypy-precommit.sh, scripts/ci/run-suite-manual.sh, scripts/security/dependency-scan.sh
- `scripts/ci/test_suites.py` — **DEV-INFRA** — refs: ci: .gitea/workflows/ci.yml, .gitea/workflows/nightly.yml, .github/workflows/ci.yml; test: tests/ci/test_manual_gate_fast_suites.py; script: scripts/ci/check_test_suite_parity.py, scripts/ci/run-suite-manual.sh; other: Makefile
- `scripts/ci/unaccounted_openapi_specs.py` — **DEV-INFRA** — refs: script: scripts/ci/check-openapi-drift.sh
- `scripts/ci/unawaited-async-baseline.txt` — **DEV-INFRA** — refs: no exact static refs
- `scripts/config/aitbc-secrets.conf` — **PRODUCT** — refs: no exact static refs
- `scripts/deployment/aitbc-logrotate.conf` — **PRODUCT** — logrotate config installed by update.sh; workflow reference is a documentation comment, not an execution dependency; XB->OPS scripts/workflow/37_contract_event_monitoring.sh; refs: test: tests/unit/test_logrotate_config.py; script: scripts/deployment/update.sh, scripts/workflow/16_monitoring_setup.sh; doc: docs/deployment/SERVICE_USERS.md
- `scripts/deployment/blockchain-communication-test.sh` — **OPS** — multi-node deployment communication probe; refs: doc: docs/releases/2026/README.md#v0515
- `scripts/deployment/create_aitbc_user.sh` — **PRODUCT** — refs: doc: docs/deployment/SERVICE_USERS.md, docs/releases/2026/README.md#v050
- `scripts/deployment/deploy.sh` — **PRODUCT** — refs: test: tests/unit/test_env_source_as_shell_2787.py; script: scripts/ci/check-shell-strict-mode.py; doc: docs/archive/security/testing-procedures.md, docs/deployment/STAGING.md, docs/releases/2026/README.md#v058
- `scripts/deployment/deploy/.env.deploy.example` — **OPS** — refs: no exact static refs
- `scripts/deployment/deploy/container-deploy.py` — **OPS** — XB->PRODUCT-SIDE scripts/deployment/setup.sh; refs: script: scripts/deployment/deploy/deploy-domain.sh; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/deployment/deploy/deploy-all-remote.sh` — **OPS** — refs: no exact static refs
- `scripts/deployment/deploy/deploy-blockchain-and-explorer.sh` — **OPS** — refs: doc: docs/deployment/bc2-consumers.md
- `scripts/deployment/deploy/deploy-blockchain-remote.sh` — **OPS** — refs: no exact static refs
- `scripts/deployment/deploy/deploy-domain.sh` — **OPS** — refs: no exact static refs
- `scripts/deployment/deploy/deploy-env.sh` — **OPS** — refs: test: tests/unit/test_deploy_blockchain_explorer_env_2781.py; script: 8 refs incl. scripts/deployment/deploy/deploy-all-remote.sh, scripts/deployment/deploy/deploy-blockchain-and-explorer.sh; doc: docs/deployment/script-environment.md
- `scripts/deployment/deploy/deploy-explorer-remote.sh` — **OPS** — refs: no exact static refs
- `scripts/deployment/deploy/deploy-explorer.sh` — **OPS** — refs: doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02311, docs/releases/2026/README.md#v02334; LEAK(operator-domain)
- `scripts/deployment/deploy/deploy-in-container.sh` — **OPS** — refs: no exact static refs
- `scripts/deployment/deploy/deploy-nginx-reverse-proxy.sh` — **OPS** — refs: doc: docs/releases/2026/README.md#v0258
- `scripts/deployment/deploy/deploy-to-aitbc-container.sh` — **OPS** — refs: no exact static refs
- `scripts/deployment/deploy/deploy-to-container.sh` — **OPS** — XB->PRODUCT-SIDE scripts/deployment/setup.sh; refs: no exact static refs
- `scripts/deployment/deploy/deploy-to-container.sh.example` — **OPS** — refs: no exact static refs
- `scripts/deployment/deploy/deploy-to-server.sh` — **OPS** — refs: doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02311; LEAK(operator-domain)
- `scripts/deployment/init_proposer.py` — **PRODUCT** — refs: script: scripts/deployment/setup.sh
- `scripts/deployment/install-profiles.sh` — **PRODUCT** — refs: script: scripts/deployment/deploy.sh, scripts/deployment/setup.sh, scripts/deployment/update.sh; doc: 10 refs incl. docs/deployment/fleet-roles.md, docs/development/2_setup.md; other: requirements-test.txt
- `scripts/deployment/run-migrations.sh` — **PRODUCT** — refs: app/cli/pkg: apps/blockchain-node/migrations/versions/9f8e7d6c5b4a_backfill_escrows_from_lock_tx.py, apps/blockchain-node/tests/test_migration_graph.py; test: apps/blockchain-node/tests/test_migration_graph.py, tests/unit/test_deploy_migrations.py; script: scripts/deployment/deploy.sh, scripts/deployment/update.sh; doc: docs/getting-started/UPDATE.md, docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/deployment/setup.sh` — **PRODUCT** — refs: test: tests/unit/test_env_source_as_shell_2787.py, tests/unit/test_setup_env_file_perms_1730.py, tests/unit/test_setup_scripts_hardening.py; script: 6 refs incl. scripts/ci/check-shell-strict-mode.py, scripts/deployment/deploy/container-deploy.py; doc: 30 refs incl. AGENTS.md, README.md; other: .secrets.baseline
- `scripts/deployment/setup_postgresql_databases.sh` — **PRODUCT** — refs: test: tests/test_backup_pg_owner.py, tests/unit/test_setup_scripts_hardening.py; script: scripts/deployment/setup.sh, scripts/workflow/02_genesis_authority_setup.sh, scripts/workflow/03_follower_node_setup.sh; doc: docs/getting-started/setup-configuration.md, docs/getting-started/setup-reference.md, docs/releases/2026/README.md#v054
- `scripts/deployment/unify_service_users.sh` — **PRODUCT** — refs: doc: docs/deployment/SERVICE_USERS.md, docs/releases/2026/README.md#v0245, docs/releases/2026/README.md#v050
- `scripts/deployment/update.sh` — **PRODUCT** — XB->OPS scripts/monitoring/deploy-rules.sh, scripts/ops/render-website.sh; refs: app/cli/pkg: cli/CLI_USAGE_GUIDE.md, cli/README.md, cli/man/aitbc.1; test: tests/cli/test_commands_update.py; script: 4 refs incl. scripts/ci/check-shell-strict-mode.py, scripts/deployment/setup.sh; doc: 8 refs incl. docs/getting-started/UPDATE.md, docs/getting-started/setup-reference.md
- `scripts/deployment/validate-env.sh` — **PRODUCT** — refs: no exact static refs
- `scripts/dev/gen_mcp_tool_inventory.py` — **DEV-INFRA** — refs: script: scripts/ci/check-mcp-cli-drift.sh, scripts/ci/check-mcp-tool-surface.py; doc: docs/reference/mcp-tool-inventory.md
- `scripts/dev/gen_option_coverage.py` — **DEV-INFRA** — refs: script: scripts/ci/manual-ci-known-red.txt; doc: docs/cli-option-uncovered.md, docs/releases/2026/README.md#v02513
- `scripts/dev/generate_mcp_cli_tools.py` — **DEV-INFRA** — refs: app/cli/pkg: 130 refs incl. mcp-server/aitbc_mcp_cli_helpers.py, mcp-server/aitbc_mcp_cli_tools_generated.py; test: tests/test_syspath_hygiene.py; script: scripts/ci/check-mcp-cli-drift.sh, scripts/ci/check-module-size.py; doc: docs/features/messaging-contracts.md, docs/releases/2026/README.md#v0256
- `scripts/dev/setup.sh` — **DEV-INFRA** — refs: doc: docs/development/5_developer-guide.md, docs/releases/2026/versions/v0.10/v0.10.10_AGENTS.md, docs/releases/2026/README.md#v01010
- `scripts/development/dev-services.sh` — **DEV-INFRA** — refs: no exact static refs
- `scripts/development/start-aitbc-dev.sh` — **DEV-INFRA** — refs: script: scripts/dev/setup.sh
- `scripts/development/start-aitbc-full.sh` — **DEV-INFRA** — refs: no exact static refs
- `scripts/development/stop-aitbc-dev.sh` — **DEV-INFRA** — refs: no exact static refs
- `scripts/docs/check_bind_policy.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; ci: .gitea/workflows/ci.yml, .github/workflows/ci.yml; script: scripts/ci/run-suite-manual.sh; doc: docs/deployment/NETWORK_POLICY.md, docs/getting-started/reference/security-notes.md
- `scripts/docs/check_docs_path_refs.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml
- `scripts/docs/check_feature_status.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; test: tests/unit/test_check_feature_status.py; doc: docs/meta/DOCUMENTATION_TEMPLATE_STANDARD.md
- `scripts/docs/check_links.py` — **DEV-INFRA** — refs: test: tests/unit/test_check_links_forms.py; script: scripts/validate_docs.sh; doc: docs/releases/2026/README.md#v0250
- `scripts/docs/check_orphan_docs.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; doc: docs/README.md
- `scripts/docs/check_ports.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; ci: .gitea/workflows/ci.yml, .github/workflows/ci.yml; script: scripts/ci/run-suite-manual.sh, scripts/development/start-aitbc-dev.sh, scripts/docs/gen_cli_command_docs.py
- `scripts/docs/docs-path-refs-baseline.txt` — **DEV-INFRA** — XB->OPS scripts/workflow/23_scaling_preparation.sh; refs: script: scripts/docs/check_docs_path_refs.py
- `scripts/docs/feature-status-baseline.txt` — **DEV-INFRA** — refs: no exact static refs
- `scripts/docs/gen_all_routes.py` — **DEV-INFRA** — refs: doc: docs/reference/all-routes.md
- `scripts/docs/gen_cli_command_docs.py` — **DEV-INFRA** — refs: script: scripts/ci/check-cli-docs.sh, scripts/ci/check-mcp-tool-surface.py, scripts/dev/generate_mcp_cli_tools.py; doc: 597 refs incl. docs/cli/commands/README.md, docs/cli/commands/account-get.md
- `scripts/docs/gen_doc_mesh.py` — **DEV-INFRA** — refs: script: scripts/ci/check-cli-docs.sh; doc: docs/reference/cli-rpc-route-map.md, docs/reference/record-types.md, docs/testing/record-type-test-map.md
- `scripts/docs/gen_master_index.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; ci: .gitea/workflows/ci.yml, .github/workflows/ci.yml; script: scripts/ci/run-suite-manual.sh; doc: docs/MASTER_INDEX.md, docs/ci-cd/README.md
- `scripts/docs/orphan-docs-baseline.txt` — **DEV-INFRA** — XB->OPS scripts/stress/KNOWN.md, scripts/stress/MATURITY.md, scripts/stress/README.md; refs: doc: docs/releases/2026/README.md#v0259
- `scripts/dump_mcp_tools.py` — **DEV-INFRA** — MCP tool inventory generator; refs: doc: docs/getting-started/SETUP.md, docs/getting-started/UPDATE.md
- `scripts/extract_openapi_specs.py` — **DEV-INFRA** — OpenAPI extraction generator used by drift gate; refs: app/cli/pkg: apps/api-gateway/src/api_gateway/main.py; script: scripts/ci/check-openapi-drift.sh; doc: 4 refs incl. docs/api/README.md, docs/apps/exchange/exchange.md; other: .gitignore, Makefile
- `scripts/generate_cli_docs.py` — **DEV-INFRA** — CLI docs generator; refs: test: tests/test_cli_docs_sync.py; script: scripts/ci/check-cli-docs.sh, scripts/docs/gen_cli_command_docs.py; doc: docs/ci-cd/README.md
- `scripts/generate_dev_keys.py` — **DEV-INFRA** — development key material generator; not production runtime; refs: doc: docs/releases/2026/versions/v0.4/v0.4.26_AGENT_A_COMPLETED.md, docs/releases/2026/README.md#v0426
- `scripts/gpu/README.md` — **PRODUCT** — refs: test: tests/unit/test_v2399_health_gate_paths.py; script: scripts/services/gpu/gpu_miner_host.py; doc: docs/architecture/edge_gpu_setup.md, docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334; other: .secrets.baseline; LEAK(operator-domain)
- `scripts/lint/no_float_money.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; app/cli/pkg: apps/blockchain-node/tests/test_signed_payload_money_is_float.py, apps/coordinator-api/alembic/versions/c7d1f4a9e230_v23_money_columns_to_numeric.py, apps/coordinator-api/alembic/versions/f2b6c04a91d8_v23_budget_columns_to_numeric.py; test: apps/blockchain-node/tests/test_signed_payload_money_is_float.py; script: 4 refs incl. scripts/ci/mypy-precommit.sh, scripts/ci/run-suite-manual.sh; doc: 4 refs incl. docs/architecture/money-types-and-the-signature-boundary.md, docs/releases/2026/README.md#v022; other: Makefile
- `scripts/lint/no_float_money_baseline.json` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml
- `scripts/lint/no_orphan_modules.py` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; test: tests/unit/test_v23103_orphan_modules.py; script: scripts/lint/no_orphan_modules_baseline.json; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/lint/no_orphan_modules_baseline.json` — **DEV-INFRA** — refs: doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/maintenance/aitbc-backup-verify.service` — **PRODUCT** — refs: doc: docs/ops/backup-assurance.md
- `scripts/maintenance/aitbc-backup-verify.timer` — **PRODUCT** — refs: doc: docs/ops/backup-assurance.md
- `scripts/maintenance/aitbc-backup.service` — **PRODUCT** — refs: script: scripts/deployment/setup.sh; doc: docs/releases/2026/README.md#v054
- `scripts/maintenance/aitbc-backup.sh` — **PRODUCT** — refs: unit: scripts/maintenance/aitbc-backup.service; app/cli/pkg: cli/aitbc_cli/core/node_client.py; test: tests/test_backup_pg_owner.py, tests/unit/test_aitbc_backup.py; script: scripts/deployment/setup.sh, scripts/maintenance/aitbc-backup.service, scripts/testing/test_coldstart_db_race.sh; doc: 9 refs incl. docs/deployment/bc2-consumers.md, docs/getting-started/UPDATE.md; LEAK(operator-domain)
- `scripts/maintenance/aitbc-backup.timer` — **PRODUCT** — refs: script: scripts/deployment/setup.sh; doc: docs/releases/2026/README.md#v054
- `scripts/migration/create_advanced_market_tables.py` — **PRODUCT** — refs: test: tests/unit/test_v23103_orphan_modules.py
- `scripts/migration/create_agent_tables.py` — **PRODUCT** — refs: no exact static refs
- `scripts/migration/migrate_plugin_to_market.py` — **PRODUCT** — refs: no exact static refs
- `scripts/migration/v0.25.7_migrate_ipfs_rentals.py` — **PRODUCT** — refs: doc: docs/releases/2026/README.md#v0257
- `scripts/monitoring/aitbc-alert-digest.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-alert-digest.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-attestation-arrival.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-attestation-arrival.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-authority-balances.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-authority-balances.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-backup-metrics.service` — **OPS** — refs: test: tests/unit/test_security_audit_root_and_perm.py
- `scripts/monitoring/aitbc-backup-metrics.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-bridge-hole-scan.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-bridge-hole-scan.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-bridge-set.service` — **OPS** — refs: test: tests/unit/test_security_audit_root_and_perm.py
- `scripts/monitoring/aitbc-bridge-set.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-cache-monitor.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-cache-monitor.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-chain-isolation-monitor.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-chain-isolation-monitor.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-dashboard.json` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-env-watch.service` — **OPS** — refs: script: scripts/security/security_audit.py
- `scripts/monitoring/aitbc-env-watch.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-escrow-residue.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-escrow-residue.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-escrow-settlements.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-escrow-settlements.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-hub-watch-deadman.service` — **OPS** — refs: script: scripts/security/security_audit.py; LEAK(operator-domain)
- `scripts/monitoring/aitbc-hub-watch-deadman.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-island-subscription-check.service` — **OPS** — refs: test: tests/unit/test_security_audit_root_and_perm.py; script: scripts/security/security_audit.py
- `scripts/monitoring/aitbc-island-subscription-check.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-island-swarm-probe.service` — **OPS** — refs: test: tests/unit/test_security_audit_root_and_perm.py
- `scripts/monitoring/aitbc-island-swarm-probe.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-journal-errors.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-journal-errors.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-memory-monitor.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-memory-monitor.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-native-energy-rate-refresh.service` — **OPS** — refs: script: scripts/testing/test_link_systemd_preserve.sh
- `scripts/monitoring/aitbc-native-energy-rate-refresh.timer` — **OPS** — refs: script: scripts/testing/test_link_systemd_preserve.sh
- `scripts/monitoring/aitbc-ntfy-bridge.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-ntfy-heartbeat-daily.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-ntfy-heartbeat-daily.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-ntfy-heartbeat-hourly.service` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-ntfy-heartbeat-hourly.timer` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc-prometheus-watch.service` — **OPS** — refs: doc: docs/getting-started/setup-service-selection.md, docs/infrastructure/monitoring-setup.md, docs/releases/2026/README.md#v0259
- `scripts/monitoring/aitbc_hub1_rules.yml` — **OPS** — refs: no exact static refs
- `scripts/monitoring/aitbc_hub_rules.yml` — **OPS** — refs: script: scripts/monitoring/aitbc_rules_test.yml; doc: 4 refs incl. docs/infrastructure/monitoring-setup.md, docs/ops/native-energy-rate-guard-deploy.md
- `scripts/monitoring/aitbc_rules.yml` — **OPS** — refs: script: scripts/monitoring/aitbc_rules_test.yml; doc: 9 refs incl. docs/deployment/bc2-alert-window.md, docs/deployment/bc2-consumers.md
- `scripts/monitoring/aitbc_rules_test.yml` — **OPS** — refs: doc: 4 refs incl. docs/deployment/bc2-consumers.md, docs/ops/v9-pre-pin-checklist.md; LEAK(operator-domain)
- `scripts/monitoring/alert-digest.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-alert-digest.service; test: tests/unit/test_alert_digest.py; script: scripts/monitoring/aitbc-alert-digest.service; doc: docs/infrastructure/monitoring-setup.md; LEAK(operator-domain)
- `scripts/monitoring/attestation-arrival-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-attestation-arrival.service; test: tests/unit/test_attestation_arrival_textfile.py; script: scripts/monitoring/aitbc-attestation-arrival.service; doc: docs/deployment/bc2-consumers.md, docs/deployment/bc2-post-ponr-failures.md, docs/infrastructure/monitoring-setup.md
- `scripts/monitoring/authority-balances-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-authority-balances.service; test: tests/unit/test_authority_balances_textfile.py; script: scripts/monitoring/aitbc-authority-balances.service, scripts/monitoring/aitbc_hub_rules.yml; doc: docs/infrastructure/monitoring-setup.md
- `scripts/monitoring/backup-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-backup-metrics.service; test: tests/unit/test_backup_textfile.py; script: scripts/monitoring/aitbc-backup-metrics.service
- `scripts/monitoring/blackbox.yml` — **OPS** — refs: no exact static refs
- `scripts/monitoring/bridge-header-hole-scan.sh` — **OPS** — refs: unit: scripts/monitoring/aitbc-bridge-hole-scan.service; script: scripts/monitoring/aitbc-bridge-hole-scan.service, scripts/testing/test_coldstart_db_race.sh
- `scripts/monitoring/bridge-payout-audit.py` — **OPS** — refs: doc: docs/ops/bridge-canary-runbook.md, docs/releases/2026/README.md#v0259
- `scripts/monitoring/bridge-set-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-bridge-set.service; test: tests/unit/test_bridge_set_textfile.py; script: scripts/monitoring/aitbc-bridge-set.service, scripts/monitoring/aitbc_hub_rules.yml; doc: docs/infrastructure/monitoring-setup.md
- `scripts/monitoring/cache-monitor.sh` — **OPS** — refs: unit: scripts/monitoring/aitbc-cache-monitor.service; script: scripts/monitoring/aitbc-cache-monitor.service
- `scripts/monitoring/check-rules-deployed.sh` — **OPS** — refs: test: tests/unit/test_check_rules_deployed.py; script: scripts/monitoring/prometheus.yml
- `scripts/monitoring/dashboard.sh` — **OPS** — refs: no exact static refs
- `scripts/monitoring/deploy-rules.sh` — **OPS** — refs: test: tests/unit/test_deploy_rules_dry_run.py; script: scripts/deployment/update.sh, scripts/monitoring/check-rules-deployed.sh; doc: docs/releases/2026/README.md#v02512
- `scripts/monitoring/env-watch-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-env-watch.service; test: tests/unit/test_env_watch_textfile.py; script: scripts/monitoring/aitbc-env-watch.service; doc: docs/deployment/bc2-consumers.md, docs/infrastructure/monitoring-setup.md
- `scripts/monitoring/escrow-known-artifacts.yml` — **OPS** — refs: script: scripts/monitoring/aitbc_rules_test.yml; doc: docs/ops/escrow-settlement-ops.md
- `scripts/monitoring/escrow-residue-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-escrow-residue.service; test: tests/unit/test_escrow_residue_dryrun.py, tests/unit/test_escrow_residue_textfile.py; script: scripts/monitoring/aitbc-escrow-residue.service, scripts/ops/escrow_residue_classify.py; doc: docs/deployment/bc2-consumers.md
- `scripts/monitoring/escrow-settlements-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-escrow-settlements.service; app/cli/pkg: apps/blockchain-node/src/aitbc_chain/rpc/escrow_settlement_sweeper_scan.py; test: tests/unit/test_escrow_settlements_textfile.py; script: scripts/monitoring/aitbc-escrow-settlements.service; doc: docs/ops/escrow-settlement-ops.md, docs/ops/legacy-escrow-residue-payout.md
- `scripts/monitoring/examples/monitor.py` — **OPS** — refs: no exact static refs
- `scripts/monitoring/examples/tests/__init__.py` — **OPS** — refs: no exact static refs
- `scripts/monitoring/fleet-config-check.sh` — **OPS** — refs: app/cli/pkg: apps/blockchain-node/src/aitbc_chain/consensus_digest.py, cli/aitbc_cli/commands/network.py; test: tests/security/test_no_fleet_details_are_published.py; script: scripts/ops/gpu-registry-sweep.py; doc: 11 refs incl. docs/cli/commands/network-gossip.md, docs/deployment/bc3-env-map.md
- `scripts/monitoring/health_check.sh` — **PRODUCT** — explicit issue ruling; product health endpoint check used by deployment/control paths; refs: app/cli/pkg: cli/aitbc_cli/commands/control.py, cli/aitbc_cli/commands/health.py, cli/tests/test_control_installed_filter.py; test: 4 refs incl. cli/tests/test_control_installed_filter.py, tests/unit/test_env_source_as_shell_2787.py; script: 8 refs incl. scripts/deployment/deploy.sh, scripts/deployment/setup.sh; doc: 13 refs incl. docs/archive/security/testing-procedures.md, docs/deployment/STAGING.md; other: health-check.sh
- `scripts/monitoring/hub-watch-deadman-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-hub-watch-deadman.service; script: scripts/monitoring/aitbc-hub-watch-deadman.service; LEAK(operator-domain)
- `scripts/monitoring/island-subscription-check.sh` — **OPS** — refs: unit: scripts/monitoring/aitbc-island-subscription-check.service; script: scripts/monitoring/aitbc-island-subscription-check.service, scripts/testing/test_link_systemd_preserve.sh
- `scripts/monitoring/island-swarm-probe-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-island-swarm-probe.service; script: scripts/monitoring/aitbc-island-swarm-probe.service; LEAK(operator-domain)
- `scripts/monitoring/journal-errors-textfile.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-journal-errors.service; test: tests/unit/test_journal_errors_textfile.py; script: scripts/monitoring/aitbc-journal-errors.service; doc: docs/infrastructure/monitoring-setup.md, docs/releases/2026/README.md#v0259
- `scripts/monitoring/memory-monitor.sh` — **OPS** — refs: unit: scripts/monitoring/aitbc-memory-monitor.service; test: tests/unit/test_memory_monitor_cgroup.py; script: scripts/monitoring/aitbc-memory-monitor.service, scripts/testing/test_memory_monitor.sh; LEAK(operator-domain)
- `scripts/monitoring/monitor-prs.py` — **OPS** — refs: doc: docs/releases/2026/versions/v0.10/v0.10.13_AGENTS.md, docs/releases/2026/README.md#v01013
- `scripts/monitoring/native-energy-rate-refresh.sh` — **OPS** — refs: unit: scripts/monitoring/aitbc-native-energy-rate-refresh.service; script: scripts/monitoring/aitbc-native-energy-rate-refresh.service, scripts/monitoring/aitbc_hub_rules.yml, scripts/testing/test_native_energy_rate_refresh.sh; doc: docs/ops/native-energy-rate-guard-deploy.md
- `scripts/monitoring/network_monitor.sh` — **OPS** — refs: no exact static refs
- `scripts/monitoring/ntfy-alert-bridge.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-ntfy-bridge.service; test: tests/unit/test_ntfy_alert_bridge.py; script: scripts/monitoring/aitbc-ntfy-bridge.service
- `scripts/monitoring/ntfy-heartbeat.py` — **OPS** — refs: unit: scripts/monitoring/aitbc-ntfy-heartbeat-daily.service, scripts/monitoring/aitbc-ntfy-heartbeat-hourly.service; test: tests/unit/test_ntfy_heartbeat.py; script: scripts/monitoring/aitbc-ntfy-heartbeat-daily.service, scripts/monitoring/aitbc-ntfy-heartbeat-hourly.service; doc: docs/infrastructure/monitoring-setup.md
- `scripts/monitoring/production_monitoring.sh` — **OPS** — XB->PRODUCT-SIDE scripts/monitoring/health_check.sh; refs: test: tests/unit/test_v23100_monitoring_targets.py; LEAK(operator-domain)
- `scripts/monitoring/prometheus.yml` — **OPS** — refs: test: tests/test_prometheus_config.py; doc: 4 refs incl. docs/DESIGN_CYCLE.md, docs/infrastructure/monitoring-setup.md; LEAK(operator-domain)
- `scripts/monitoring/setup-contract-monitoring.sh` — **OPS** — refs: doc: docs/deployment/SMART_CONTRACT_DEPLOYMENT.md
- `scripts/monitoring/state-digest-remote.py` — **OPS** — refs: doc: docs/releases/2026/README.md#v0258
- `scripts/monitoring/state-digest-spec.py` — **OPS** — refs: app/cli/pkg: apps/blockchain-node/tests/test_fleet_digest_spec.py; test: apps/blockchain-node/tests/test_fleet_digest_spec.py; script: scripts/monitoring/fleet-config-check.sh; doc: docs/releases/2026/README.md#v0258
- `scripts/monitoring/verify-monitoring.sh` — **OPS** — refs: doc: docs/deployment/SMART_CONTRACT_DEPLOYMENT.md
- `scripts/monitoring/verify_chain_isolation.sh` — **OPS** — refs: unit: scripts/monitoring/aitbc-chain-isolation-monitor.service; script: scripts/monitoring/aitbc-chain-isolation-monitor.service
- `scripts/notifications/config.sh` — **DEV-INFRA** — template for contract deployment notification/API environment; not node runtime; refs: no exact static refs
- `scripts/openapi_error_responses.py` — **DEV-INFRA** — OpenAPI helper consumed by extraction/drift tooling; refs: app/cli/pkg: apps/blockchain-node/src/aitbc_chain/rpc/routers/cross_chain.py; test: tests/unit/test_openapi_error_responses.py; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/ops/ait-reference-price.py` — **OPS** — refs: app/cli/pkg: aitbc/market/reference_price.py, aitbc/oracles/price_oracle.py; doc: docs/getting-started/ait-value-model.md, docs/ops/pricing-energy-exchange.md, docs/releases/2026/README.md#v0259; other: website/exchange.html, website/reference.json
- `scripts/ops/backfill-follower-gap.sh` — **OPS** — refs: app/cli/pkg: apps/blockchain-node/src/aitbc_chain/proposer_identity.py; test: tests/unit/test_backfill_follower_gap.py; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334; LEAK(operator-domain)
- `scripts/ops/backup-verify.py` — **PRODUCT** — per-node backup verification invoked by aitbc-backup-verify.service; relocate near maintenance; refs: unit: scripts/maintenance/aitbc-backup-verify.service; test: tests/test_backup_verify.py; script: scripts/maintenance/aitbc-backup-verify.service; doc: docs/ops/backup-assurance.md, docs/ops/backup-restore.md, docs/releases/2026/README.md#v0260
- `scripts/ops/bridge-admin.sh` — **OPS** — refs: app/cli/pkg: apps/bridge-monitor/README.md, apps/bridge-monitor/src/bridge_monitor/admin.py, cli/aitbc_cli/commands/bridge/_ledger.py; doc: 9 refs incl. AGENTS.md, docs/cli/commands/bridge-deposits.md
- `scripts/ops/bridge-leaf-audit.py` — **OPS** — refs: app/cli/pkg: apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_lock_guard.py, apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_root_shadow.py; test: tests/unit/test_bridge_leaf_audit.py; script: scripts/ci/manual-ci-known-red.txt; doc: docs/deployment/bc2-consumers.md, docs/design/bridge-state-root-grandfathering.md
- `scripts/ops/bridge-transplant.sh` — **OPS** — refs: doc: docs/ops/bridge-release-exercise.md
- `scripts/ops/bridge_mainnet_preflight.py` — **OPS** — refs: test: tests/unit/test_bridge_mainnet_preflight.py; doc: docs/contracts/cross-chain-bridge-deployment.md, docs/releases/2026/README.md#v02511
- `scripts/ops/bridge_outbound_collect.py` — **OPS** — refs: test: tests/unit/test_bridge_outbound_collect.py; doc: docs/ops/bridge-funding-source-migration.md, docs/ops/bridge-outbound-ledger-migration-runbook.md, docs/ops/messaging-series-rollout.md
- `scripts/ops/bridge_outbound_migration_dryrun.py` — **OPS** — refs: test: tests/unit/test_bridge_outbound_migration_dryrun.py; doc: docs/ops/bridge-outbound-ledger-migration-runbook.md
- `scripts/ops/bridge_proof_dryrun.py` — **OPS** — refs: test: tests/unit/test_bridge_proof_dryrun.py
- `scripts/ops/bridge_set_vs_consensus.py` — **OPS** — refs: test: tests/unit/test_bridge_set_vs_consensus.py
- `scripts/ops/bridge_validators_compare.py` — **OPS** — refs: test: tests/unit/test_bridge_validators_compare.py
- `scripts/ops/bridge_wallet_reconcile.py` — **OPS** — refs: test: tests/unit/test_bridge_wallet_reconcile.py; script: scripts/ops/bridge_outbound_migration_dryrun.py; doc: docs/ops/bridge-outbound-ledger-migration-runbook.md
- `scripts/ops/bridge_wallet_rotation_report.py` — **OPS** — refs: test: tests/unit/test_bridge_wallet_rotation_report.py; doc: docs/ops/node-sepolia-wallets.md
- `scripts/ops/build-genesis.py` — **PRODUCT** — canonical genesis builder needed to create/join islands; product utilities and reset harness reference it; refs: app/cli/pkg: 7 refs incl. aitbc/utils/reset_guard.py, apps/blockchain-node/create_enhanced_genesis.py; test: tests/cli/test_commands_genesis.py; script: 5 refs incl. scripts/ops/create-genesis-block.py, scripts/ops/reset-follower-to-genesis.sh; doc: 7 refs incl. docs/cli/commands/README.md, docs/cli/commands/genesis-init.md
- `scripts/ops/check-alloc-file.py` — **PRODUCT** — genesis allocation validator pinned by product tests/docs; refs: test: tests/unit/test_bc2_genesis_files.py, tests/unit/test_check_alloc_file.py; script: scripts/ci/manual-ci-known-red.txt; doc: 5 refs incl. docs/deployment/bc2-genesis/README.md, docs/deployment/bc2-reset-runbook.md
- `scripts/ops/create-genesis-block.py` — **OPS** — XB->PRODUCT-SIDE scripts/ops/build-genesis.py; refs: script: scripts/utils/genesis-init.py
- `scripts/ops/env-set-plan.py` — **OPS** — refs: doc: docs/deployment/bc2-environment-set.md
- `scripts/ops/escrow-repair.py` — **OPS** — refs: test: tests/unit/test_escrow_repair.py; doc: docs/design/escrow-rebuild-from-chain.md
- `scripts/ops/escrow-stuck-sweep.py` — **OPS** — refs: test: tests/unit/test_escrow_stuck_sweep.py; script: scripts/ci/manual-ci-known-red.txt; doc: docs/ops/escrow-relays.md
- `scripts/ops/escrow_residue_classify.py` — **OPS** — refs: test: tests/unit/test_escrow_residue_classify_2925.py; script: scripts/monitoring/escrow-residue-textfile.py
- `scripts/ops/escrow_residue_dryrun.py` — **OPS** — refs: test: tests/unit/test_escrow_residue_dryrun.py; script: scripts/monitoring/aitbc_rules.yml, scripts/ops/escrow_residue_classify.py
- `scripts/ops/exchange-ticks-preflight.py` — **PRODUCT** — product upgrade migration preflight; refs: app/cli/pkg: apps/exchange/simple_exchange/db.py
- `scripts/ops/exchange_verify.py` — **PRODUCT** — aitbc exchange verify CLI locates and executes this script; refs: app/cli/pkg: cli/aitbc_cli/commands/exchange/hub_orders.py, cli/tests/test_exchange_verify.py, mcp-server/aitbc_mcp_cli_tools_generated_exchange.py; test: cli/tests/test_exchange_verify.py, tests/unit/test_exchange_verify.py; doc: 7 refs incl. docs/apps/exchange/exchange.md, docs/cli/commands/README.md
- `scripts/ops/failover-gen.py` — **OPS** — refs: test: tests/test_failover_gen_proto.py; doc: docs/ops/failover-runbook.md
- `scripts/ops/failover-preflight.sh` — **OPS** — refs: test: tests/test_failover_preflight.py; doc: docs/getting-started/UPDATE.md, docs/ops/failover-runbook.md, docs/ops/fleet-wave-runbook.md
- `scripts/ops/failover-readback.sh` — **OPS** — refs: test: tests/unit/test_failover_readback.py; doc: docs/ops/failover-runbook.md, docs/releases/2026/README.md#v0280; LEAK(operator-domain)
- `scripts/ops/first-sweep-check.py` — **OPS** — refs: test: tests/unit/test_first_sweep_check.py; doc: docs/deployment/bc2-consumers.md, docs/ops/first-sweep-observation.md
- `scripts/ops/fix-x-forwarded-proto.sh` — **OPS** — refs: no exact static refs
- `scripts/ops/gen-window-ledger.py` — **OPS** — refs: test: tests/test_gen_window_ledger.py
- `scripts/ops/governance_parameter_change.py` — **OPS** — refs: app/cli/pkg: apps/blockchain-node/tests/test_bridge_tx_root_1940.py, apps/blockchain-node/tests/test_governance_execute_rehearsal.py; test: apps/blockchain-node/tests/test_bridge_tx_root_1940.py, apps/blockchain-node/tests/test_governance_execute_rehearsal.py, tests/unit/test_governance_parameter_change.py; doc: docs/releases/2026/README.md#v02510; LEAK(operator-domain)
- `scripts/ops/gpu-registry-sweep.py` — **OPS** — refs: app/cli/pkg: apps/blockchain-node/src/aitbc_chain/config_consensus.py; test: tests/unit/test_cleanup_fake_gpus_retired.py, tests/unit/test_gpu_registry_sweep.py; script: scripts/ops/replay-chain.py; LEAK(operator-domain)
- `scripts/ops/hold-check.sh` — **OPS** — refs: test: tests/test_hold_check.py; doc: docs/getting-started/UPDATE.md, docs/ops/fleet-wave-runbook.md
- `scripts/ops/host-compare.py` — **OPS** — refs: test: tests/test_host_compare.py
- `scripts/ops/key-audit.py` — **PRODUCT** — aitbc-backup.sh invokes key audit before backup; relocate with backup tooling; refs: script: scripts/maintenance/aitbc-backup.sh; doc: 6 refs incl. docs/deployment/bc3-genesis/README.md, docs/deployment/reset2-runbook.md
- `scripts/ops/key_residue_census.py` — **OPS** — refs: test: tests/unit/test_key_residue_census.py; doc: docs/releases/2026/README.md#v02511
- `scripts/ops/manage-peer-keys.sh` — **PRODUCT** — open-island peer-key lifecycle tooling; refs: app/cli/pkg: apps/blockchain-node/src/aitbc_chain/rpc/peer_keys.py; doc: docs/agent/guides/open-island-joining-guide.md, docs/deployment/bc2-environment-set.md, docs/ops/peer-keys.md
- `scripts/ops/offsite-pull-backups.service` — **OPS** — refs: script: scripts/security/security_audit.py
- `scripts/ops/offsite-pull-backups.sh` — **OPS** — refs: unit: scripts/ops/offsite-pull-backups.service; test: tests/unit/test_offsite_pull_backups.py; script: scripts/ops/offsite-pull-backups.service; doc: docs/ops/backup-restore.md
- `scripts/ops/offsite-pull-backups.timer` — **OPS** — refs: no exact static refs
- `scripts/ops/ops_http.py` — **OPS** — refs: script: scripts/ci/manual-ci-known-red.txt; doc: docs/releases/2026/README.md#v0260
- `scripts/ops/option-coverage-exclusions.json` — **DEV-INFRA** — data consumed by option-coverage generator; refs: test: tests/test_option_coverage.py; script: scripts/ops/option-coverage.py; doc: docs/scenarios/85_secret_forms.md
- `scripts/ops/option-coverage.py` — **DEV-INFRA** — scenario/operator-option coverage documentation generator; refs: test: tests/test_option_coverage.py; script: scripts/ci/manual-ci-known-red.txt; doc: docs/releases/2026/README.md#v0260, docs/scenarios/80_required_flags.md
- `scripts/ops/post-cut-verify.py` — **OPS** — refs: test: tests/test_post_cut_verify.py; script: scripts/ci/manual-ci-known-red.txt; doc: docs/ops/chain-reset-runbook.md
- `scripts/ops/post_activation_audit.py` — **OPS** — refs: test: tests/unit/test_post_activation_audit.py; script: scripts/ci/manual-ci-known-red.txt; doc: docs/deployment/bc2-consumers.md, docs/ops/v14-activation-runbook.md; LEAK(operator-domain)
- `scripts/ops/post_cut_checks.py` — **OPS** — refs: no exact static refs
- `scripts/ops/rebuild-escrows.py` — **OPS** — refs: test: tests/unit/test_rebuild_escrows.py; doc: docs/design/escrow-rebuild-from-chain.md
- `scripts/ops/reconcile-operations.py` — **OPS** — refs: doc: docs/releases/2026/README.md#v0257
- `scripts/ops/register_bridge_validators.py` — **OPS** — refs: test: tests/test_register_bridge_validators.py, tests/unit/test_register_bridge_validators_file_source.py; doc: docs/deployment/bc2-environment-set.json, docs/deployment/bc2-environment-set.md
- `scripts/ops/render-bootstrap-env.sh` — **PRODUCT** — open-island bootstrap env renderer used by joining flow; refs: app/cli/pkg: apps/blockchain-node/src/aitbc_chain/app.py; other: examples/blockchain.env.open-island, examples/nginx/nginx-aitbc.conf.example, website/README.md
- `scripts/ops/render-website.sh` — **OPS** — refs: test: tests/unit/test_render_website.py; script: scripts/deployment/update.sh; doc: 5 refs incl. AGENTS.md, docs/deployment/bc2-consumers.md; other: examples/website.env.example, website/README.md; LEAK(operator-domain)
- `scripts/ops/replay-chain.py` — **OPS** — refs: test: tests/test_replay_chain.py, tests/unit/test_replay_chain.py; script: scripts/ops/gpu-registry-sweep.py; doc: docs/ops/v5-replay-inventory.md, docs/releases/2026/README.md#v0258, docs/releases/2026/README.md#v0259; LEAK(operator-domain)
- `scripts/ops/reset-follower-to-genesis.sh` — **OPS** — XB->PRODUCT-SIDE scripts/ops/build-genesis.py; refs: doc: docs/releases/2026/README.md#v0241
- `scripts/ops/reset-follower-to-snapshot.sh` — **OPS** — SSH-orchestrated fleet follower recovery with hub root access and internal default HUB; product sync_divergence reference is a break-point; refs: app/cli/pkg: apps/blockchain-node/src/aitbc_chain/sync_divergence.py; script: scripts/monitoring/aitbc_hub_rules.yml; doc: docs/agent/guides/open-island-joining-guide.md; LEAK(operator-domain)
- `scripts/ops/rotate_api_key_secret.sh` — **OPS** — refs: no exact static refs
- `scripts/ops/rotate_jwt_secret.sh` — **OPS** — refs: doc: docs/deployment/environment-configuration.md
- `scripts/ops/secret_scan.py` — **DEV-INFRA** — repository secret scanning gate/helper; refs: no exact static refs
- `scripts/ops/sepolia_balance.py` — **OPS** — refs: test: tests/unit/test_sepolia_balance.py; doc: docs/ops/node-sepolia-wallets.md, docs/scenarios/59_sepolia_buy_sell_ait.md
- `scripts/ops/side-root-probe.py` — **PRODUCT** — executable canonical digest reference mirrored by product side_root_shadow; refs: app/cli/pkg: apps/blockchain-node/src/aitbc_chain/state/side_root_shadow.py; test: tests/unit/test_side_root_probe.py; script: scripts/stress/plays/15-committed-table.sh; doc: docs/design/v3-side-table-root-shadow.md
- `scripts/ops/sign-snapshot-manifest.py` — **PRODUCT** — snapshot publication tool for hub operators; refs: test: tests/unit/test_snapshot_manifest_signing.py
- `scripts/ops/snapshot-manifest.py` — **PRODUCT** — snapshot manifest generation/inspection for product snapshot sync; refs: test: tests/unit/test_snapshot_manifest.py
- `scripts/ops/stamp-website-assets.py` — **PRODUCT** — explicit issue ruling; relocate to scripts/ci because website-asset-stamp hook invokes it; refs: test: tests/unit/test_website_asset_stamp.py; script: scripts/ci/check-website-stamp.sh; doc: docs/releases/2026/README.md#v02511
- `scripts/ops/sync-website-menu.py` — **DEV-INFRA** — website/docs navigation synchronization utility; refs: test: tests/unit/test_website_menu_consistency.py; doc: docs/releases/2026/README.md#v02511
- `scripts/ops/unpause-precheck.py` — **OPS** — refs: test: tests/test_unpause_precheck.py; script: scripts/ci/manual-ci-known-red.txt; doc: docs/deployment/bc2-reset-runbook.md
- `scripts/ops/v17-activation-verify.sh` — **OPS** — refs: test: tests/unit/test_v17_activation_verify.py
- `scripts/ops/verify-genesis-root.py` — **PRODUCT** — join-time genesis verification tool; refs: test: tests/unit/test_verify_genesis_root.py; doc: docs/agent/guides/open-island-joining-guide.md, docs/ops/companion-island-deploy.md
- `scripts/ops/verify-snapshot-manifest.py` — **PRODUCT** — snapshot attestation verification consumed by recovery/join tooling; refs: doc: docs/agent/guides/open-island-joining-guide.md
- `scripts/ops/wallets-perms-audit.py` — **OPS** — refs: test: tests/test_wallets_perms_audit.py
- `scripts/ops/watch_drift_check.py` — **OPS** — refs: test: tests/unit/test_watch_drift_check.py; doc: docs/releases/2026/README.md#v02511
- `scripts/ops/website-375-check.js` — **DEV-INFRA** — website rendering/check utility; refs: test: tests/unit/test_website_layout_375.py; doc: docs/releases/2026/README.md#v02511
- `scripts/performance/run_load_tests.sh` — **DEV-INFRA** — CI/load-test workflow runner with thresholds; refs: test: tests/conftest.py, tests/load/conftest.py; doc: docs/releases/2026/README.md#v050
- `scripts/quality/audit_cli_help.py` — **DEV-INFRA** — refs: no exact static refs
- `scripts/release/append-changelog.sh` — **DEV-INFRA** — refs: no exact static refs
- `scripts/release/check-v0.5.0.sh` — **DEV-INFRA** — refs: test: tests/unit/test_check_v050_release_gate.py; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/reset-harness/gossip_filter.py` — **OPS** — refs: script: scripts/ci/manual-ci-known-red.txt
- `scripts/reset-harness/rehearsal.py` — **OPS** — XB->PRODUCT-SIDE scripts/ops/build-genesis.py; refs: test: tests/test_reset_harness.py; script: scripts/ci/manual-ci-known-red.txt, scripts/ci/module-size-baseline.txt; doc: docs/ops/chain-reset-runbook.md, docs/ops/companion-island-deploy.md
- `scripts/reset-harness/rehearsal_keys.py` — **OPS** — refs: no exact static refs
- `scripts/reset-harness/rollback.py` — **OPS** — refs: doc: docs/deployment/bc2-reset-runbook.md, docs/ops/chain-reset-runbook.md; LEAK(operator-domain)
- `scripts/security/aitbc-security-nightly.service` — **OPS** — fleet-scheduled security audit unit; XB->PRODUCT-SIDE scripts/security/nightly-security.sh; refs: script: scripts/security/security_audit.py
- `scripts/security/aitbc-security-nightly.timer` — **OPS** — fleet schedule for security-nightly service; refs: no exact static refs
- `scripts/security/dependency-scan.sh` — **DEV-INFRA** — dependency vulnerability scan for engineering/CI use; refs: ci: .github/SECURITY.md; test: tests/test_dependency_security.py; doc: 6 refs incl. docs/getting-started/installation/installation.md, docs/releases/2026/README.md#v0410
- `scripts/security/migrate_secrets_to_env_files.py` — **PRODUCT** — refs: other: .secrets.baseline
- `scripts/security/mutation_spots.py` — **DEV-INFRA** — mutation-testing target analyzer; refs: script: scripts/security/nightly-security.sh
- `scripts/security/nightly-security.sh` — **DEV-INFRA** — security test-suite orchestrator; fleet timer pairing is OPS but the suite itself is engineering verification; refs: ci: .gitea/workflows/nightly.yml; unit: scripts/security/aitbc-security-nightly.service; script: scripts/security/aitbc-security-nightly.service
- `scripts/security/scan_secrets.py` — **DEV-INFRA** — repository secret scanner; refs: ci: .github/SECURITY.md; script: scripts/ci/check_deprecation_cleanup.sh; doc: docs/releases/RELEASE_PREP.md, docs/releases/2026/versions/v0.11/v0.11.0_AGENTS.md, docs/releases/2026/README.md#v0161
- `scripts/security/security_audit.py` — **PRODUCT** — XB->OPS scripts/monitoring/aitbc-env-watch.service, scripts/monitoring/aitbc-hub-watch-deadman.service, scripts/monitoring/aitbc-island-subscription-check.service, scripts/ops/offsite-pull-backups.service, scripts/security/aitbc-security-nightly.service; refs: ci: .github/SECURITY.md; test: tests/test_security_audit_paths.py; doc: 4 refs incl. docs/archive/security/SECURITY_FIXES_SUMMARY.md, docs/getting-started/installation/installation.md
- `scripts/security/security_monitor.sh` — **PRODUCT** — refs: no exact static refs
- `scripts/service-management/check-container.sh` — **OPS** — refs: no exact static refs
- `scripts/service-management/diagnose-services.sh` — **OPS** — refs: no exact static refs
- `scripts/service-management/fix-services.sh` — **OPS** — refs: doc: docs/releases/2026/versions/v0.4/v0.4.27_AGENT_B.md, docs/releases/2026/README.md#v0427
- `scripts/service-management/lib/services.sh` — **OPS** — XB->PRODUCT-SIDE scripts/monitoring/health_check.sh; refs: script: scripts/ci/check-shell-strict-mode.py; other: .secrets.baseline
- `scripts/service-management/run-local-services.sh` — **OPS** — refs: doc: docs/releases/2026/README.md#v0426; LEAK(operator-domain)
- `scripts/service-management/stop-services.sh` — **OPS** — refs: doc: docs/releases/2026/versions/v0.4/v0.4.27_AGENT_B.md, docs/releases/2026/README.md#v0427
- `scripts/services/agent-coordinator-wrapper.py` — **PRODUCT** — refs: no exact static refs
- `scripts/services/gpu/gpu_exchange_status.py` — **DEV-INFRA** — demo/diagnostic probe pinned by tests; not service runtime; refs: no exact static refs
- `scripts/services/gpu/gpu_miner_host.py` — **PRODUCT** — refs: script: scripts/docs/docs-path-refs-baseline.txt; doc: docs/architecture/edge_gpu_setup.md, docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/services/gpu/integrate_gpu_exchange.py` — **DEV-INFRA** — obsolete developer integration example that prints guidance; refs: no exact static refs
- `scripts/services/gpu/miner.spec` — **DEV-INFRA** — PyInstaller packaging spec for miner binary; refs: doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/setup/install-nginx-node.sh` — **PRODUCT** — refs: test: tests/unit/test_install_nginx_1023.py; doc: docs/releases/2026/README.md#v0249, docs/releases/2026/README.md#v045
- `scripts/setup/install-system-deps.sh` — **PRODUCT** — refs: no exact static refs
- `scripts/stress/KNOWN.md` — **OPS** — refs: script: scripts/docs/orphan-docs-baseline.txt; doc: docs/deployment/reset2-runbook.md
- `scripts/stress/MATURITY.md` — **OPS** — refs: script: scripts/docs/orphan-docs-baseline.txt
- `scripts/stress/README.md` — **OPS** — refs: script: scripts/docs/orphan-docs-baseline.txt; LEAK(operator-domain)
- `scripts/stress/baseline.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/lib.sh` — **OPS** — refs: test: tests/unit/test_stress_refusal_class.py, tests/unit/test_stress_spend_guard.py; LEAK(operator-domain)
- `scripts/stress/maturity-watcher.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/01-transfers.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/02-messaging.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/03-ai-job.sh` — **OPS** — refs: no exact static refs; LEAK(operator-domain)
- `scripts/stress/plays/04-escrow.sh` — **OPS** — refs: no exact static refs; LEAK(operator-domain)
- `scripts/stress/plays/05-gpu.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/06-market.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/07-agent-staking.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/08-bounty.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/09-bond.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/10-liquidity.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/11-bond-release.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/12-bridge.sh` — **OPS** — refs: no exact static refs; LEAK(operator-domain)
- `scripts/stress/plays/13-governance.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/14-island.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/15-committed-table.sh` — **OPS** — XB->PRODUCT-SIDE scripts/ops/side-root-probe.py; refs: no exact static refs
- `scripts/stress/plays/16-nonce-storm.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/17-restart-under-load.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/18-wedge-replay.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/20-fee-sweep.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/21-ipfs-subscribe.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/22-exchange-anchor.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/23-bond-slash.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/plays/24-bonded-job-slash.sh` — **OPS** — refs: no exact static refs; LEAK(operator-domain)
- `scripts/stress/preflight.sh` — **OPS** — refs: no exact static refs; LEAK(operator-domain)
- `scripts/stress/run.sh` — **OPS** — refs: no exact static refs
- `scripts/stress/watch.sh` — **OPS** — refs: no exact static refs
- `scripts/sync/sync_detector.sh` — **OPS** — refs: no exact static refs
- `scripts/templates/service-wrapper.py.j2` — **DEV-INFRA** — refs: no exact static refs
- `scripts/testing/chaos_orchestrator.py` — **OPS** — chaos/failure-injection orchestration against deployed services; refs: test: tests/unit/test_chaos_orchestrator.py
- `scripts/testing/chaos_test_coordinator.py` — **OPS** — chaos scenario against coordinator service; refs: no exact static refs
- `scripts/testing/chaos_test_database.py` — **OPS** — chaos scenario against database availability; refs: other: .secrets.baseline
- `scripts/testing/chaos_test_network.py` — **OPS** — chaos/failure-injection network scenario; refs: no exact static refs
- `scripts/testing/qa-cycle.py` — **DEV-INFRA** — engineering QA/review automation rather than node runtime; refs: doc: 5 refs incl. docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/testing/quick_test.py` — **PRODUCT** — refs: no exact static refs; LEAK(operator-domain)
- `scripts/testing/run_all_tests.sh` — **OPS** — multi-site/fleet test runner; refs: doc: docs/releases/2026/README.md#v0241
- `scripts/testing/run_load_tests.sh` — **DEV-INFRA** — engineering load-test runner; not required for node runtime; refs: test: tests/README.md
- `scripts/testing/scalability_validation.py` — **PRODUCT** — refs: test: tests/unit/test_scalability_validation.py; doc: docs/releases/2026/versions/v0.4/v0.4.16_SECURITY_FIXES.md, docs/releases/2026/versions/v0.4/v0.4.16_changelog.md; LEAK(operator-domain)
- `scripts/testing/soak_test_consensus.py` — **PRODUCT** — refs: doc: docs/releases/2026/README.md#v075
- `scripts/testing/test_coldstart_db_race.sh` — **OPS** — cold-start race harness primarily pins OPS bridge-header scan; product backup coverage must be duplicated or split; XB->PRODUCT-SIDE scripts/maintenance/aitbc-backup.sh; refs: no exact static refs
- `scripts/testing/test_disabled_services_guard.sh` — **PRODUCT** — refs: doc: docs/ops/fleet-is-hub-semantics.md; other: Makefile
- `scripts/testing/test_link_systemd_preserve.sh` — **PRODUCT** — pin for PRODUCT link-systemd sweep semantics; OPS unit names are fixture cases to generalize during carve-out; XB->OPS scripts/monitoring/aitbc-native-energy-rate-refresh.service, scripts/monitoring/aitbc-native-energy-rate-refresh.timer, scripts/monitoring/island-subscription-check.sh; refs: other: Makefile; LEAK(operator-domain)
- `scripts/testing/test_memory_monitor.sh` — **OPS** — live test of OPS memory monitor; refs: other: Makefile
- `scripts/testing/test_native_energy_rate_refresh.sh` — **OPS** — live test of OPS native-energy refresh timer; refs: other: Makefile
- `scripts/testing/test_workflow.sh` — **PRODUCT** — refs: no exact static refs
- `scripts/utils/agent_followup.sh` — **PRODUCT** — refs: test: tests/unit/test_env_source_as_shell_2787.py; script: 5 refs incl. scripts/ci/check-shell-strict-mode.py, scripts/deployment/install-profiles.sh
- `scripts/utils/aitbc-load-secrets.service` — **PRODUCT** — refs: doc: docs/releases/2026/versions/v0.5/v0.5.0_systemd-hardening-report.md
- `scripts/utils/aitbc-recovery.service` — **PRODUCT** — refs: script: scripts/security/security_audit.py; doc: 4 refs incl. docs/releases/2026/versions/v0.5/v0.5.11_AGENTS.md, docs/releases/2026/versions/v0.5/v0.5.11_agent-b.md
- `scripts/utils/chain_regen_node.py` — **OPS** — destructive chain-state regeneration/recovery runbook tool; refs: test: tests/unit/test_chain_regen_node.py; doc: docs/releases/2026/versions/v0.4/v0.4.25_SYSPATH_DEBT.md
- `scripts/utils/check-dependencies.sh` — **PRODUCT** — refs: doc: docs/getting-started/installation/installation.md, docs/getting-started/overview/cli-guide.md
- `scripts/utils/claim-task.py` — **OPS** — internal gitea issue-lane claiming tool; refs: doc: docs/releases/2026/versions/v0.10/v0.10.13_AGENTS.md, docs/releases/2026/README.md#v01013
- `scripts/utils/clean-sudoers-fix.sh` — **PRODUCT** — refs: no exact static refs
- `scripts/utils/common.sh` — **OPS** — legacy multi-node mesh workflow helper library; refs: no exact static refs
- `scripts/utils/create_structured_issue.py` — **OPS** — internal gitea issue creation/tooling; refs: no exact static refs
- `scripts/utils/deploy_common.sh` — **PRODUCT** — refs: script: scripts/deployment/setup.sh
- `scripts/utils/dev-constraints.sh` — **PRODUCT** — refs: test: tests/test_requirements_tiers.py; script: scripts/deployment/install-profiles.sh, scripts/deployment/setup.sh
- `scripts/utils/encrypt_keystore_password.py` — **PRODUCT** — refs: doc: docs/releases/2026/versions/v0.4/v0.4.25_SYSPATH_DEBT.md
- `scripts/utils/end_to_end_workflow.py` — **OPS** — live multi-service end-to-end scenario; refs: doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/utils/env_config.sh` — **OPS** — legacy multi-node mesh workflow configuration helper; refs: test: tests/test_env_config.py; script: scripts/ci/check-shell-strict-mode.py
- `scripts/utils/fix-permissions.sh` — **DEV-INFRA** — developer checkout permission repair helper; refs: script: scripts/utils/setup-dev-permissions.sh
- `scripts/utils/generate-api-keys.py` — **DEV-INFRA** — test/development API-key generator; refs: doc: docs/archive/security/SECURITY_FIXES_SUMMARY.md, docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/utils/genesis-init.py` — **OPS** — legacy/historical chain initialization and reset helper; refs: test: tests/unit/test_genesis_legacy_guards.py; doc: docs/deployment/bc2-consumers.md
- `scripts/utils/git-pre-commit-hook.sh` — **DEV-INFRA** — developer hook installation/helper; refs: test: tests/test_git_pre_commit_hook.py
- `scripts/utils/harden-systemd-services.py` — **DEV-INFRA** — one-off source-tree systemd hardening migration; refs: test: tests/unit/test_harden_systemd_services.py; doc: docs/releases/2026/README.md#v050, docs/releases/2026/README.md#v058, docs/releases/2026/README.md#v059
- `scripts/utils/init_production_genesis.py` — **OPS** — historical production genesis initializer; XB->PRODUCT-SIDE scripts/ops/build-genesis.py; refs: test: tests/unit/test_genesis_legacy_guards.py; doc: docs/deployment/bc2-consumers.md, docs/releases/2026/versions/v0.4/v0.4.25_SYSPATH_DEBT.md
- `scripts/utils/install-path-packages.sh` — **PRODUCT** — refs: app/cli/pkg: mcp-server/sync-venv.sh; script: scripts/deployment/setup.sh, scripts/deployment/update.sh, scripts/dev/setup.sh
- `scripts/utils/keystore.py` — **PRODUCT** — refs: test: tests/unit/test_keystore_util.py
- `scripts/utils/link-systemd.sh` — **PRODUCT** — refs: unit: scripts/utils/aitbc-recovery.service; script: 6 refs incl. scripts/deployment/deploy.sh, scripts/deployment/setup.sh; doc: 12 refs incl. docs/agent/guides/open-island-joining-guide.md, docs/getting-started/UPDATE.md
- `scripts/utils/load-keystore-secrets.sh` — **PRODUCT** — refs: unit: scripts/utils/aitbc-load-secrets.service, scripts/utils/aitbc-recovery.service; script: 4 refs incl. scripts/deployment/deploy.sh, scripts/deployment/setup.sh; doc: 8 refs incl. docs/archive/security/SECURITY_FIXES_SUMMARY.md, docs/getting-started/SETUP.md
- `scripts/utils/manage-services.sh` — **OPS** — fleet/service control helper coupled to sync.sh deploy action; refs: script: scripts/utils/sync.sh
- `scripts/utils/migrate_addresses_to_0x.py` — **PRODUCT** — refs: test: tests/unit/test_migrate_addresses_0x.py
- `scripts/utils/migrate_secrets_to_keystore.py` — **PRODUCT** — refs: doc: docs/releases/2026/versions/v0.4/v0.4.25_SYSPATH_DEBT.md
- `scripts/utils/organize-dev-logs.sh` — **DEV-INFRA** — development log organization helper; refs: doc: docs/development/DEV_LOGS.md
- `scripts/utils/reset_chain_0x.py` — **OPS** — destructive chain reset helper for fleet operations; refs: test: tests/unit/test_reset_chain_0x_genesis.py; other: .secrets.baseline
- `scripts/utils/rotate_service_accounts.py` — **OPS** — fleet wallet/account rotation operation; refs: test: tests/test_rotate_service_accounts.py; other: .secrets.baseline
- `scripts/utils/run_comprehensive_planning_cleanup.sh` — **OPS** — internal documentation/planning cleanup operation; refs: no exact static refs
- `scripts/utils/security_hardening.sh` — **PRODUCT** — refs: test: tests/unit/test_security_hardening.py; doc: docs/getting-started/installation/installation.md, docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334; LEAK(operator-domain)
- `scripts/utils/setup-credentials.py` — **PRODUCT** — refs: doc: docs/archive/security/SECURITY_FIXES_SUMMARY.md
- `scripts/utils/setup-dev-permissions.sh` — **DEV-INFRA** — development workstation permission setup; refs: no exact static refs
- `scripts/utils/sync.sh` — **OPS** — gitea-to-GitHub mirror/fleet synchronization tool; refs: no exact static refs
- `scripts/utils/systemd-env.sh` — **PRODUCT** — refs: test: tests/unit/test_deploy_env_parsing.py, tests/unit/test_env_source_as_shell_2787.py, tests/unit/test_validate_env.py; script: 8 refs incl. scripts/deployment/deploy.sh, scripts/deployment/run-migrations.sh
- `scripts/utils/validate-requirements.sh` — **PRODUCT** — refs: doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334
- `scripts/utils/verify-db-schema.py` — **PRODUCT** — refs: script: scripts/deployment/run-migrations.sh
- `scripts/utils/workspace-manager.sh` — **OPS** — internal agent workspace lifecycle manager; refs: doc: docs/releases/2026/versions/v0.10/v0.10.13_AGENTS.md, docs/releases/2026/README.md#v01013
- `scripts/validate_docs.sh` — **DEV-INFRA** — pre-commit docs validator; refs: hook: .pre-commit-config.yaml; ci: .gitea/workflows/ci.yml, .github/pull_request_template.md, .github/workflows/ci.yml; script: scripts/ci/run-suite-manual.sh; doc: 4 refs incl. docs/CONTRIBUTING.md, docs/audit/DOCS_REFRESH_AUDIT.md
- `scripts/workflow/01_preflight_setup.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py; doc: docs/deployment/bc2-environment-set.md
- `scripts/workflow/02_genesis_authority_setup.sh` — **OPS** — XB->PRODUCT-SIDE scripts/deployment/setup_postgresql_databases.sh, scripts/ops/build-genesis.py; refs: test: tests/unit/test_utils_setup_production_retired.py; doc: docs/deployment/bc2-consumers.md
- `scripts/workflow/03_follower_node_setup.sh` — **OPS** — XB->PRODUCT-SIDE scripts/deployment/setup.sh, scripts/deployment/setup_postgresql_databases.sh; refs: test: tests/unit/test_workflow_preflight.py; script: scripts/workflow/23_scaling_preparation.sh
- `scripts/workflow/04_create_wallet.sh` — **OPS** — refs: no exact static refs
- `scripts/workflow/05_send_transaction.sh` — **OPS** — refs: no exact static refs
- `scripts/workflow/06_final_verification.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py
- `scripts/workflow/07_enterprise_automation.sh` — **OPS** — refs: no exact static refs
- `scripts/workflow/13_maintenance_automation.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py
- `scripts/workflow/15_service_optimization.sh` — **OPS** — refs: no exact static refs
- `scripts/workflow/16_monitoring_setup.sh` — **OPS** — XB->PRODUCT-SIDE scripts/deployment/aitbc-logrotate.conf; refs: test: tests/unit/test_workflow_preflight.py
- `scripts/workflow/17_security_hardening.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py
- `scripts/workflow/18_production_readiness.sh` — **OPS** — refs: no exact static refs
- `scripts/workflow/21_maintenance_automation.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py
- `scripts/workflow/22_advanced_monitoring.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py
- `scripts/workflow/23_scaling_preparation.sh` — **OPS** — refs: script: scripts/docs/docs-path-refs-baseline.txt; doc: docs/deployment/script-environment.md
- `scripts/workflow/24_market_scenario.sh` — **OPS** — refs: no exact static refs
- `scripts/workflow/24_market_scenario_real.sh` — **OPS** — refs: no exact static refs
- `scripts/workflow/25_comprehensive_testing.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py
- `scripts/workflow/27_operations_automation.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py
- `scripts/workflow/31_consensus_testing.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py
- `scripts/workflow/33_enhanced_contract_service_testing.sh` — **OPS** — refs: no exact static refs
- `scripts/workflow/34_service_health_monitoring.sh` — **OPS** — refs: script: scripts/workflow/41_complete_optimization_workflow.sh
- `scripts/workflow/36_contract_security_testing.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py; script: scripts/workflow/41_complete_optimization_workflow.sh
- `scripts/workflow/37_contract_event_monitoring.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py; script: scripts/deployment/aitbc-logrotate.conf, scripts/workflow/41_complete_optimization_workflow.sh
- `scripts/workflow/38_contract_data_analytics.sh` — **OPS** — refs: test: tests/unit/test_workflow_preflight.py; script: scripts/workflow/41_complete_optimization_workflow.sh
- `scripts/workflow/41_complete_optimization_workflow.sh` — **OPS** — refs: no exact static refs
- `scripts/workflow/README.md` — **OPS** — refs: doc: docs/README.md
- `scripts/workflow/setup_multinode_blockchain.sh` — **OPS** — refs: doc: docs/deployment/bc2-consumers.md
- `scripts/zk/build-circuits.sh` — **DEV-INFRA** — refs: hook: .pre-commit-config.yaml; app/cli/pkg: apps/zk-circuits/README.md; test: tests/unit/test_v2395_zk_circuit_tree_parity.py; doc: docs/releases/2026/README.md#v023, docs/releases/2026/README.md#v02334, docs/releases/2026/README.md#v02414

## LEAK inventory for scrub pass

**34 files** under `scripts/` contain the specified internal-topology tokens. The scan found operator-domain occurrences; no `fleet-prefix-a` or `fleet-prefix-b` literals were present in this checkout. Classification does not change the scrub requirement for anything remaining PRODUCT-side.

| file | class | tokens |
|---|---|---|
| `scripts/ci/run-suite-manual.sh` | DEV-INFRA | operator-domain |
| `scripts/deployment/deploy/deploy-explorer.sh` | OPS | operator-domain |
| `scripts/deployment/deploy/deploy-to-server.sh` | OPS | operator-domain |
| `scripts/gpu/README.md` | PRODUCT | operator-domain |
| `scripts/maintenance/aitbc-backup.sh` | PRODUCT | operator-domain |
| `scripts/monitoring/aitbc-hub-watch-deadman.service` | OPS | operator-domain |
| `scripts/monitoring/aitbc_rules_test.yml` | OPS | operator-domain |
| `scripts/monitoring/alert-digest.py` | OPS | operator-domain |
| `scripts/monitoring/hub-watch-deadman-textfile.py` | OPS | operator-domain |
| `scripts/monitoring/island-swarm-probe-textfile.py` | OPS | operator-domain |
| `scripts/monitoring/memory-monitor.sh` | OPS | operator-domain |
| `scripts/monitoring/production_monitoring.sh` | OPS | operator-domain |
| `scripts/monitoring/prometheus.yml` | OPS | operator-domain |
| `scripts/ops/backfill-follower-gap.sh` | OPS | operator-domain |
| `scripts/ops/failover-readback.sh` | OPS | operator-domain |
| `scripts/ops/governance_parameter_change.py` | OPS | operator-domain |
| `scripts/ops/gpu-registry-sweep.py` | OPS | operator-domain |
| `scripts/ops/post_activation_audit.py` | OPS | operator-domain |
| `scripts/ops/render-website.sh` | OPS | operator-domain |
| `scripts/ops/replay-chain.py` | OPS | operator-domain |
| `scripts/ops/reset-follower-to-snapshot.sh` | OPS | operator-domain |
| `scripts/reset-harness/rollback.py` | OPS | operator-domain |
| `scripts/service-management/run-local-services.sh` | OPS | operator-domain |
| `scripts/stress/README.md` | OPS | operator-domain |
| `scripts/stress/lib.sh` | OPS | operator-domain |
| `scripts/stress/plays/03-ai-job.sh` | OPS | operator-domain |
| `scripts/stress/plays/04-escrow.sh` | OPS | operator-domain |
| `scripts/stress/plays/12-bridge.sh` | OPS | operator-domain |
| `scripts/stress/plays/24-bonded-job-slash.sh` | OPS | operator-domain |
| `scripts/stress/preflight.sh` | OPS | operator-domain |
| `scripts/testing/quick_test.py` | PRODUCT | operator-domain |
| `scripts/testing/scalability_validation.py` | PRODUCT | operator-domain |
| `scripts/testing/test_link_systemd_preserve.sh` | PRODUCT | operator-domain |
| `scripts/utils/security_hardening.sh` | PRODUCT | operator-domain |

## High-priority carve-out break-points

- `scripts/deployment/update.sh` **executes** OPS-classified `scripts/monitoring/deploy-rules.sh` and `scripts/ops/render-website.sh`. This is a real invocation dependency, not a documentation mention; Phase 4 must make both optional/pluggable or move replacement product-safe implementations in.
- `scripts/utils/link-systemd.sh` is PRODUCT but its role model and reconcile sweep manage **40 monitoring units plus OPS/security backup timer units** by basename. The references are unit names rather than script-path literals, so the exact-path scan under-reports this coupling. Moving those units requires a role-model/relink migration in the same fleet pass.
- `scripts/maintenance/aitbc-backup.service`/`aitbc-backup-verify.service` are PRODUCT per ruling, but `aitbc-backup.sh` invokes `scripts/ops/key-audit.py` and the verify unit executes `scripts/ops/backup-verify.py`. Both scripts are classified PRODUCT here and must relocate out of `ops/` or the path coupling remains misleading.
- The `website-asset-stamp` hook survives only because `scripts/ops/stamp-website-assets.py` is PRODUCT and relocates to `scripts/ci` per the ruling; leaving the current path in place preserves an `ops/` dependency in a product-side gate.
- Product runtime/docstring surfaces mention OPS operator scripts: `sync_divergence.py` names `reset-follower-to-snapshot.sh`; bridge docs/code name `bridge-admin.sh`; consensus/config modules name fleet audit/sweep scripts. Most are operator instructions rather than subprocess calls, but they still break public operator flow and must be rewritten or given product-safe replacements.
- Reverse dependencies exist too: OPS reset/workflow/security units reference PRODUCT-side genesis, backup, health, or nightly-test scripts. Because both repos must verify self-contained, Phase 3/4 must either copy the needed product helpers into ops, move the pins, or explicitly retain a read-only product-repo dependency in the ops deployment model.
- `scripts/testing/test_link_systemd_preserve.sh` is a PRODUCT pin with OPS unit fixture names; `scripts/testing/test_coldstart_db_race.sh` is OPS but also covers PRODUCT backup behavior. Both need split/generalized coverage rather than a naive file move.
- Tracked root symlink `health-check.sh` points at `/opt/aitbc/scripts/monitoring/health_check.sh`. It is outside `scripts/` but is a direct checkout-level dependency on the PRODUCT health script path.

## PRODUCT-side break-points: references into OPS

- `scripts/deployment/aitbc-logrotate.conf` statically references OPS-classified: `scripts/workflow/37_contract_event_monitoring.sh`
- `scripts/deployment/update.sh` statically references OPS-classified: `scripts/monitoring/deploy-rules.sh`, `scripts/ops/render-website.sh`
- `scripts/security/security_audit.py` statically references OPS-classified: `scripts/monitoring/aitbc-env-watch.service`, `scripts/monitoring/aitbc-hub-watch-deadman.service`, `scripts/monitoring/aitbc-island-subscription-check.service`, `scripts/ops/offsite-pull-backups.service`, `scripts/security/aitbc-security-nightly.service`
- `scripts/testing/test_link_systemd_preserve.sh` statically references OPS-classified: `scripts/monitoring/aitbc-native-energy-rate-refresh.service`, `scripts/monitoring/aitbc-native-energy-rate-refresh.timer`, `scripts/monitoring/island-subscription-check.sh`

## Outside-`scripts/` static references to OPS-classified scripts

`RUNTIME` below means the referencing file lives in the product runtime tree (`apps/`, `cli/`, `packages/`, `aitbc/`, `mcp-server/`); it does **not** by itself prove subprocess execution — many are docstring/operator-instruction references that still break documentation or operator flow after a carve-out.
- `scripts/audit/reconcile_agent_wallets.py` <= docs 1: `docs/releases/2026/versions/v0.12/v0.12.0_AGENTS.md`
- `scripts/deployment/blockchain-communication-test.sh` <= docs 1: `docs/releases/2026/README.md#v0515`
- `scripts/deployment/deploy/container-deploy.py` <= docs 2: `docs/releases/2026/README.md#v023`, `docs/releases/2026/README.md#v02334`
- `scripts/deployment/deploy/deploy-blockchain-and-explorer.sh` <= docs 1: `docs/deployment/bc2-consumers.md`
- `scripts/deployment/deploy/deploy-env.sh` <= tests 1: `tests/unit/test_deploy_blockchain_explorer_env_2781.py`; docs 1: `docs/deployment/script-environment.md`
- `scripts/deployment/deploy/deploy-explorer.sh` <= docs 3: `docs/releases/2026/README.md#v023`, `docs/releases/2026/README.md#v02311`, `docs/releases/2026/README.md#v02334`
- `scripts/deployment/deploy/deploy-nginx-reverse-proxy.sh` <= docs 1: `docs/releases/2026/README.md#v0258`
- `scripts/deployment/deploy/deploy-to-server.sh` <= docs 2: `docs/releases/2026/README.md#v023`, `docs/releases/2026/README.md#v02311`
- `scripts/monitoring/aitbc-backup-metrics.service` <= tests 1: `tests/unit/test_security_audit_root_and_perm.py`
- `scripts/monitoring/aitbc-bridge-set.service` <= tests 1: `tests/unit/test_security_audit_root_and_perm.py`
- `scripts/monitoring/aitbc-island-subscription-check.service` <= tests 1: `tests/unit/test_security_audit_root_and_perm.py`
- `scripts/monitoring/aitbc-island-swarm-probe.service` <= tests 1: `tests/unit/test_security_audit_root_and_perm.py`
- `scripts/monitoring/aitbc-prometheus-watch.service` <= docs 3: `docs/getting-started/setup-service-selection.md`, `docs/infrastructure/monitoring-setup.md`, `docs/releases/2026/README.md#v0259`
- `scripts/monitoring/aitbc_hub_rules.yml` <= docs 4: `docs/infrastructure/monitoring-setup.md`, `docs/ops/native-energy-rate-guard-deploy.md`, `docs/releases/2026/README.md#v02510`, `docs/releases/2026/README.md#v02511`
- `scripts/monitoring/aitbc_rules.yml` <= docs 9: `docs/deployment/bc2-alert-window.md`, `docs/deployment/bc2-consumers.md`, `docs/infrastructure/monitoring-setup.md`, `docs/ops/escrow-relays.md` +5 more
- `scripts/monitoring/aitbc_rules_test.yml` <= docs 4: `docs/deployment/bc2-consumers.md`, `docs/ops/v9-pre-pin-checklist.md`, `docs/releases/2026/README.md#v02511`, `docs/releases/2026/README.md#v0258`
- `scripts/monitoring/alert-digest.py` <= tests 1: `tests/unit/test_alert_digest.py`; docs 1: `docs/infrastructure/monitoring-setup.md`
- `scripts/monitoring/attestation-arrival-textfile.py` <= tests 1: `tests/unit/test_attestation_arrival_textfile.py`; docs 3: `docs/deployment/bc2-consumers.md`, `docs/deployment/bc2-post-ponr-failures.md`, `docs/infrastructure/monitoring-setup.md`
- `scripts/monitoring/authority-balances-textfile.py` <= tests 1: `tests/unit/test_authority_balances_textfile.py`; docs 1: `docs/infrastructure/monitoring-setup.md`
- `scripts/monitoring/backup-textfile.py` <= tests 1: `tests/unit/test_backup_textfile.py`
- `scripts/monitoring/bridge-payout-audit.py` <= docs 2: `docs/ops/bridge-canary-runbook.md`, `docs/releases/2026/README.md#v0259`
- `scripts/monitoring/bridge-set-textfile.py` <= tests 1: `tests/unit/test_bridge_set_textfile.py`; docs 1: `docs/infrastructure/monitoring-setup.md`
- `scripts/monitoring/check-rules-deployed.sh` <= tests 1: `tests/unit/test_check_rules_deployed.py`
- `scripts/monitoring/deploy-rules.sh` <= tests 1: `tests/unit/test_deploy_rules_dry_run.py`; docs 1: `docs/releases/2026/README.md#v02512`
- `scripts/monitoring/env-watch-textfile.py` <= tests 1: `tests/unit/test_env_watch_textfile.py`; docs 2: `docs/deployment/bc2-consumers.md`, `docs/infrastructure/monitoring-setup.md`
- `scripts/monitoring/escrow-known-artifacts.yml` <= docs 1: `docs/ops/escrow-settlement-ops.md`
- `scripts/monitoring/escrow-residue-textfile.py` <= tests 2: `tests/unit/test_escrow_residue_dryrun.py`, `tests/unit/test_escrow_residue_textfile.py`; docs 1: `docs/deployment/bc2-consumers.md`
- `scripts/monitoring/escrow-settlements-textfile.py` <= RUNTIME `apps/blockchain-node/src/aitbc_chain/rpc/escrow_settlement_sweeper_scan.py`; tests 1: `tests/unit/test_escrow_settlements_textfile.py`; docs 2: `docs/ops/escrow-settlement-ops.md`, `docs/ops/legacy-escrow-residue-payout.md`
- `scripts/monitoring/fleet-config-check.sh` <= RUNTIME `apps/blockchain-node/src/aitbc_chain/consensus_digest.py`, `cli/aitbc_cli/commands/network.py`; tests 1: `tests/security/test_no_fleet_details_are_published.py`; docs 11: `docs/cli/commands/network-gossip.md`, `docs/deployment/bc3-env-map.md`, `docs/deployment/script-environment.md`, `docs/design/v18-deterministic-committed-apply.md` +7 more
- `scripts/monitoring/journal-errors-textfile.py` <= tests 1: `tests/unit/test_journal_errors_textfile.py`; docs 2: `docs/infrastructure/monitoring-setup.md`, `docs/releases/2026/README.md#v0259`
- `scripts/monitoring/memory-monitor.sh` <= tests 1: `tests/unit/test_memory_monitor_cgroup.py`
- `scripts/monitoring/monitor-prs.py` <= docs 2: `docs/releases/2026/versions/v0.10/v0.10.13_AGENTS.md`, `docs/releases/2026/README.md#v01013`
- `scripts/monitoring/native-energy-rate-refresh.sh` <= docs 1: `docs/ops/native-energy-rate-guard-deploy.md`
- `scripts/monitoring/ntfy-alert-bridge.py` <= tests 1: `tests/unit/test_ntfy_alert_bridge.py`
- `scripts/monitoring/ntfy-heartbeat.py` <= tests 1: `tests/unit/test_ntfy_heartbeat.py`; docs 1: `docs/infrastructure/monitoring-setup.md`
- `scripts/monitoring/production_monitoring.sh` <= tests 1: `tests/unit/test_v23100_monitoring_targets.py`
- `scripts/monitoring/prometheus.yml` <= tests 1: `tests/test_prometheus_config.py`; docs 4: `docs/DESIGN_CYCLE.md`, `docs/infrastructure/monitoring-setup.md`, `docs/releases/2026/README.md#v023`, `docs/releases/2026/README.md#v02334`
- `scripts/monitoring/setup-contract-monitoring.sh` <= docs 1: `docs/deployment/SMART_CONTRACT_DEPLOYMENT.md`
- `scripts/monitoring/state-digest-remote.py` <= docs 1: `docs/releases/2026/README.md#v0258`
- `scripts/monitoring/state-digest-spec.py` <= tests 1: `apps/blockchain-node/tests/test_fleet_digest_spec.py`; docs 1: `docs/releases/2026/README.md#v0258`
- `scripts/monitoring/verify-monitoring.sh` <= docs 1: `docs/deployment/SMART_CONTRACT_DEPLOYMENT.md`
- `scripts/ops/ait-reference-price.py` <= RUNTIME `aitbc/market/reference_price.py`, `aitbc/oracles/price_oracle.py`; docs 3: `docs/getting-started/ait-value-model.md`, `docs/ops/pricing-energy-exchange.md`, `docs/releases/2026/README.md#v0259`; other `website/exchange.html`, `website/reference.json`
- `scripts/ops/backfill-follower-gap.sh` <= RUNTIME `apps/blockchain-node/src/aitbc_chain/proposer_identity.py`; tests 1: `tests/unit/test_backfill_follower_gap.py`; docs 2: `docs/releases/2026/README.md#v023`, `docs/releases/2026/README.md#v02334`
- `scripts/ops/bridge-admin.sh` <= RUNTIME `apps/bridge-monitor/README.md`, `apps/bridge-monitor/src/bridge_monitor/admin.py`, `cli/aitbc_cli/commands/bridge/_ledger.py`; docs 9: `AGENTS.md`, `docs/cli/commands/bridge-deposits.md`, `docs/ops/bridge-canary-runbook.md`, `docs/ops/bridge-funding-source-migration.md` +5 more
- `scripts/ops/bridge-leaf-audit.py` <= RUNTIME `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_lock_guard.py`, `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_root_shadow.py`; tests 1: `tests/unit/test_bridge_leaf_audit.py`; docs 2: `docs/deployment/bc2-consumers.md`, `docs/design/bridge-state-root-grandfathering.md`
- `scripts/ops/bridge-transplant.sh` <= docs 1: `docs/ops/bridge-release-exercise.md`
- `scripts/ops/bridge_mainnet_preflight.py` <= tests 1: `tests/unit/test_bridge_mainnet_preflight.py`; docs 2: `docs/contracts/cross-chain-bridge-deployment.md`, `docs/releases/2026/README.md#v02511`
- `scripts/ops/bridge_outbound_collect.py` <= tests 1: `tests/unit/test_bridge_outbound_collect.py`; docs 3: `docs/ops/bridge-funding-source-migration.md`, `docs/ops/bridge-outbound-ledger-migration-runbook.md`, `docs/ops/messaging-series-rollout.md`
- `scripts/ops/bridge_outbound_migration_dryrun.py` <= tests 1: `tests/unit/test_bridge_outbound_migration_dryrun.py`; docs 1: `docs/ops/bridge-outbound-ledger-migration-runbook.md`
- `scripts/ops/bridge_proof_dryrun.py` <= tests 1: `tests/unit/test_bridge_proof_dryrun.py`
- `scripts/ops/bridge_set_vs_consensus.py` <= tests 1: `tests/unit/test_bridge_set_vs_consensus.py`
- `scripts/ops/bridge_validators_compare.py` <= tests 1: `tests/unit/test_bridge_validators_compare.py`
- `scripts/ops/bridge_wallet_reconcile.py` <= tests 1: `tests/unit/test_bridge_wallet_reconcile.py`; docs 1: `docs/ops/bridge-outbound-ledger-migration-runbook.md`
- `scripts/ops/bridge_wallet_rotation_report.py` <= tests 1: `tests/unit/test_bridge_wallet_rotation_report.py`; docs 1: `docs/ops/node-sepolia-wallets.md`
- `scripts/ops/env-set-plan.py` <= docs 1: `docs/deployment/bc2-environment-set.md`
- `scripts/ops/escrow-repair.py` <= tests 1: `tests/unit/test_escrow_repair.py`; docs 1: `docs/design/escrow-rebuild-from-chain.md`
- `scripts/ops/escrow-stuck-sweep.py` <= tests 1: `tests/unit/test_escrow_stuck_sweep.py`; docs 1: `docs/ops/escrow-relays.md`
- `scripts/ops/escrow_residue_classify.py` <= tests 1: `tests/unit/test_escrow_residue_classify_2925.py`
- `scripts/ops/escrow_residue_dryrun.py` <= tests 1: `tests/unit/test_escrow_residue_dryrun.py`
- `scripts/ops/failover-gen.py` <= tests 1: `tests/test_failover_gen_proto.py`; docs 1: `docs/ops/failover-runbook.md`
- `scripts/ops/failover-preflight.sh` <= tests 1: `tests/test_failover_preflight.py`; docs 3: `docs/getting-started/UPDATE.md`, `docs/ops/failover-runbook.md`, `docs/ops/fleet-wave-runbook.md`
- `scripts/ops/failover-readback.sh` <= tests 1: `tests/unit/test_failover_readback.py`; docs 2: `docs/ops/failover-runbook.md`, `docs/releases/2026/README.md#v0280`
- `scripts/ops/first-sweep-check.py` <= tests 1: `tests/unit/test_first_sweep_check.py`; docs 2: `docs/deployment/bc2-consumers.md`, `docs/ops/first-sweep-observation.md`
- `scripts/ops/gen-window-ledger.py` <= tests 1: `tests/test_gen_window_ledger.py`
- `scripts/ops/governance_parameter_change.py` <= tests 3: `apps/blockchain-node/tests/test_bridge_tx_root_1940.py`, `apps/blockchain-node/tests/test_governance_execute_rehearsal.py`, `tests/unit/test_governance_parameter_change.py`; docs 1: `docs/releases/2026/README.md#v02510`
- `scripts/ops/gpu-registry-sweep.py` <= RUNTIME `apps/blockchain-node/src/aitbc_chain/config_consensus.py`; tests 2: `tests/unit/test_cleanup_fake_gpus_retired.py`, `tests/unit/test_gpu_registry_sweep.py`
- `scripts/ops/hold-check.sh` <= tests 1: `tests/test_hold_check.py`; docs 2: `docs/getting-started/UPDATE.md`, `docs/ops/fleet-wave-runbook.md`
- `scripts/ops/host-compare.py` <= tests 1: `tests/test_host_compare.py`
- `scripts/ops/key_residue_census.py` <= tests 1: `tests/unit/test_key_residue_census.py`; docs 1: `docs/releases/2026/README.md#v02511`
- `scripts/ops/offsite-pull-backups.sh` <= tests 1: `tests/unit/test_offsite_pull_backups.py`; docs 1: `docs/ops/backup-restore.md`
- `scripts/ops/ops_http.py` <= docs 1: `docs/releases/2026/README.md#v0260`
- `scripts/ops/post-cut-verify.py` <= tests 1: `tests/test_post_cut_verify.py`; docs 1: `docs/ops/chain-reset-runbook.md`
- `scripts/ops/post_activation_audit.py` <= tests 1: `tests/unit/test_post_activation_audit.py`; docs 2: `docs/deployment/bc2-consumers.md`, `docs/ops/v14-activation-runbook.md`
- `scripts/ops/rebuild-escrows.py` <= tests 1: `tests/unit/test_rebuild_escrows.py`; docs 1: `docs/design/escrow-rebuild-from-chain.md`
- `scripts/ops/reconcile-operations.py` <= docs 1: `docs/releases/2026/README.md#v0257`
- `scripts/ops/register_bridge_validators.py` <= tests 2: `tests/test_register_bridge_validators.py`, `tests/unit/test_register_bridge_validators_file_source.py`; docs 2: `docs/deployment/bc2-environment-set.json`, `docs/deployment/bc2-environment-set.md`
- `scripts/ops/render-website.sh` <= tests 1: `tests/unit/test_render_website.py`; docs 5: `AGENTS.md`, `docs/deployment/bc2-consumers.md`, `docs/deployment/bc2-reset-runbook.md`, `docs/deployment/environment-configuration.md` +1 more; other `examples/website.env.example`, `website/README.md`
- `scripts/ops/replay-chain.py` <= tests 2: `tests/test_replay_chain.py`, `tests/unit/test_replay_chain.py`; docs 3: `docs/ops/v5-replay-inventory.md`, `docs/releases/2026/README.md#v0258`, `docs/releases/2026/README.md#v0259`
- `scripts/ops/reset-follower-to-genesis.sh` <= docs 1: `docs/releases/2026/README.md#v0241`
- `scripts/ops/reset-follower-to-snapshot.sh` <= RUNTIME `apps/blockchain-node/src/aitbc_chain/sync_divergence.py`; docs 1: `docs/agent/guides/open-island-joining-guide.md`
- `scripts/ops/rotate_jwt_secret.sh` <= docs 1: `docs/deployment/environment-configuration.md`
- `scripts/ops/sepolia_balance.py` <= tests 1: `tests/unit/test_sepolia_balance.py`; docs 2: `docs/ops/node-sepolia-wallets.md`, `docs/scenarios/59_sepolia_buy_sell_ait.md`
- `scripts/ops/unpause-precheck.py` <= tests 1: `tests/test_unpause_precheck.py`; docs 1: `docs/deployment/bc2-reset-runbook.md`
- `scripts/ops/v17-activation-verify.sh` <= tests 1: `tests/unit/test_v17_activation_verify.py`
- `scripts/ops/wallets-perms-audit.py` <= tests 1: `tests/test_wallets_perms_audit.py`
- `scripts/ops/watch_drift_check.py` <= tests 1: `tests/unit/test_watch_drift_check.py`; docs 1: `docs/releases/2026/README.md#v02511`
- `scripts/reset-harness/rehearsal.py` <= tests 1: `tests/test_reset_harness.py`; docs 2: `docs/ops/chain-reset-runbook.md`, `docs/ops/companion-island-deploy.md`
- `scripts/reset-harness/rollback.py` <= docs 2: `docs/deployment/bc2-reset-runbook.md`, `docs/ops/chain-reset-runbook.md`
- `scripts/service-management/fix-services.sh` <= docs 2: `docs/releases/2026/versions/v0.4/v0.4.27_AGENT_B.md`, `docs/releases/2026/README.md#v0427`
- `scripts/service-management/lib/services.sh` <= other `.secrets.baseline`
- `scripts/service-management/run-local-services.sh` <= docs 1: `docs/releases/2026/README.md#v0426`
- `scripts/service-management/stop-services.sh` <= docs 2: `docs/releases/2026/versions/v0.4/v0.4.27_AGENT_B.md`, `docs/releases/2026/README.md#v0427`
- `scripts/stress/KNOWN.md` <= docs 1: `docs/deployment/reset2-runbook.md`
- `scripts/stress/lib.sh` <= tests 2: `tests/unit/test_stress_refusal_class.py`, `tests/unit/test_stress_spend_guard.py`
- `scripts/testing/chaos_orchestrator.py` <= tests 1: `tests/unit/test_chaos_orchestrator.py`
- `scripts/testing/chaos_test_database.py` <= other `.secrets.baseline`
- `scripts/testing/run_all_tests.sh` <= docs 1: `docs/releases/2026/README.md#v0241`
- `scripts/testing/test_memory_monitor.sh` <= other `Makefile`
- `scripts/testing/test_native_energy_rate_refresh.sh` <= other `Makefile`
- `scripts/utils/chain_regen_node.py` <= tests 1: `tests/unit/test_chain_regen_node.py`; docs 1: `docs/releases/2026/versions/v0.4/v0.4.25_SYSPATH_DEBT.md`
- `scripts/utils/claim-task.py` <= docs 2: `docs/releases/2026/versions/v0.10/v0.10.13_AGENTS.md`, `docs/releases/2026/README.md#v01013`
- `scripts/utils/end_to_end_workflow.py` <= docs 2: `docs/releases/2026/README.md#v023`, `docs/releases/2026/README.md#v02334`
- `scripts/utils/env_config.sh` <= tests 1: `tests/test_env_config.py`
- `scripts/utils/genesis-init.py` <= tests 1: `tests/unit/test_genesis_legacy_guards.py`; docs 1: `docs/deployment/bc2-consumers.md`
- `scripts/utils/init_production_genesis.py` <= tests 1: `tests/unit/test_genesis_legacy_guards.py`; docs 2: `docs/deployment/bc2-consumers.md`, `docs/releases/2026/versions/v0.4/v0.4.25_SYSPATH_DEBT.md`
- `scripts/utils/reset_chain_0x.py` <= tests 1: `tests/unit/test_reset_chain_0x_genesis.py`; other `.secrets.baseline`
- `scripts/utils/rotate_service_accounts.py` <= tests 1: `tests/test_rotate_service_accounts.py`; other `.secrets.baseline`
- `scripts/utils/workspace-manager.sh` <= docs 2: `docs/releases/2026/versions/v0.10/v0.10.13_AGENTS.md`, `docs/releases/2026/README.md#v01013`
- `scripts/workflow/01_preflight_setup.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`; docs 1: `docs/deployment/bc2-environment-set.md`
- `scripts/workflow/02_genesis_authority_setup.sh` <= tests 1: `tests/unit/test_utils_setup_production_retired.py`; docs 1: `docs/deployment/bc2-consumers.md`
- `scripts/workflow/03_follower_node_setup.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/06_final_verification.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/13_maintenance_automation.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/16_monitoring_setup.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/17_security_hardening.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/21_maintenance_automation.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/22_advanced_monitoring.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/23_scaling_preparation.sh` <= docs 1: `docs/deployment/script-environment.md`
- `scripts/workflow/25_comprehensive_testing.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/27_operations_automation.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/31_consensus_testing.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/36_contract_security_testing.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/37_contract_event_monitoring.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/38_contract_data_analytics.sh` <= tests 1: `tests/unit/test_workflow_preflight.py`
- `scripts/workflow/README.md` <= docs 1: `docs/README.md`
- `scripts/workflow/setup_multinode_blockchain.sh` <= docs 1: `docs/deployment/bc2-consumers.md`

## Systemd unit inventory and symlink deployment

`scripts/utils/link-systemd.sh` deploys units as **symlinks** into `${AITBC_SYSTEMD_DIR:-/etc/systemd/system}` pointing back into the checkout. It scans `apps/*/aitbc-*.service|timer` and `scripts/*/aitbc-*.service|timer`; it also links matching `<unit>.d` drop-in directories when present, reconciles stale repo links, enables timers/services, and is role-aware. Therefore every unit matching those globs is checkout-symlink-deployable; units outside the naming/depth pattern are not. Static inventory count: **82** unit files, all matching the symlinkable pattern.

| unit | owning area | class of owning script area | symlinked into checkout? | notes |
|---|---|---|---|---|
| `apps/agent-coordinator/aitbc-agent-coordinator.service` | `apps/agent-coordinator` | PRODUCT | yes |  |
| `apps/ai-engine/aitbc-ai.service` | `apps/ai-engine` | PRODUCT | yes |  |
| `apps/ai-engine/aitbc-learning.service` | `apps/ai-engine` | PRODUCT | yes |  |
| `apps/ai-engine/aitbc-modality-optimization.service` | `apps/ai-engine` | PRODUCT | yes |  |
| `apps/ai-engine/aitbc-multimodal.service` | `apps/ai-engine` | PRODUCT | yes |  |
| `apps/api-gateway/aitbc-api-gateway.service` | `apps/api-gateway` | PRODUCT | yes |  |
| `apps/blockchain-event-bridge/aitbc-blockchain-event-bridge.service` | `apps/blockchain-event-bridge` | PRODUCT | yes |  |
| `apps/blockchain-explorer/aitbc-blockchain-explorer.service` | `apps/blockchain-explorer` | PRODUCT | yes |  |
| `apps/blockchain-node/aitbc-blockchain-node-island.service` | `apps/blockchain-node` | PRODUCT | yes |  |
| `apps/blockchain-node/aitbc-blockchain-node.service` | `apps/blockchain-node` | PRODUCT | yes |  |
| `apps/blockchain-node/aitbc-blockchain-p2p.service` | `apps/blockchain-node` | PRODUCT | yes |  |
| `apps/blockchain-node/aitbc-blockchain-rpc-island.service` | `apps/blockchain-node` | PRODUCT | yes |  |
| `apps/blockchain-node/aitbc-blockchain-rpc.service` | `apps/blockchain-node` | PRODUCT | yes |  |
| `apps/bridge-monitor/aitbc-bridge-monitor.service` | `apps/bridge-monitor` | PRODUCT | yes |  |
| `apps/coordinator-api/aitbc-coordinator-api.service` | `apps/coordinator-api` | PRODUCT | yes |  |
| `apps/edge/aitbc-edge.service` | `apps/edge` | PRODUCT | yes |  |
| `apps/exchange/aitbc-exchange.service` | `apps/exchange` | PRODUCT | yes |  |
| `apps/ffmpeg/aitbc-ffmpeg.service` | `apps/ffmpeg` | PRODUCT | yes |  |
| `apps/governance/aitbc-governance.service` | `apps/governance` | PRODUCT | yes |  |
| `apps/gpu/aitbc-gpu.service` | `apps/gpu` | PRODUCT | yes |  |
| `apps/hermes_agent/aitbc-hermes-agent.service` | `apps/hermes_agent` | PRODUCT | yes |  |
| `apps/ipfs/aitbc-ipfs.service` | `apps/ipfs` | PRODUCT | yes |  |
| `apps/ipfs/aitbc-island-ipfs.service` | `apps/ipfs` | PRODUCT | yes |  |
| `apps/market/aitbc-market.service` | `apps/market` | PRODUCT | yes |  |
| `apps/miner/aitbc-miner.service` | `apps/miner` | PRODUCT | yes |  |
| `apps/monitoring-service/aitbc-monitoring.service` | `apps/monitoring-service` | PRODUCT | yes |  |
| `apps/ollama_gate/aitbc-ollama-gate.service` | `apps/ollama_gate` | PRODUCT | yes |  |
| `apps/ops-signer/aitbc-ops-signer.service` | `apps/ops-signer` | PRODUCT | yes |  |
| `apps/pool-hub/aitbc-pool-hub.service` | `apps/pool-hub` | PRODUCT | yes |  |
| `apps/trading/aitbc-trading.service` | `apps/trading` | PRODUCT | yes |  |
| `apps/wallet/aitbc-wallet.service` | `apps/wallet` | PRODUCT | yes |  |
| `apps/whisper/aitbc-whisper.service` | `apps/whisper` | PRODUCT | yes |  |
| `scripts/maintenance/aitbc-backup-verify.service` | `scripts/maintenance` | PRODUCT | yes | backup/maintenance unit |
| `scripts/maintenance/aitbc-backup-verify.timer` | `scripts/maintenance` | PRODUCT | yes | timer activation unit; service pair expected |
| `scripts/maintenance/aitbc-backup.service` | `scripts/maintenance` | PRODUCT | yes | backup/maintenance unit |
| `scripts/maintenance/aitbc-backup.timer` | `scripts/maintenance` | PRODUCT | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-alert-digest.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-alert-digest.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-attestation-arrival.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-attestation-arrival.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-authority-balances.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-authority-balances.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-backup-metrics.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-backup-metrics.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-bridge-hole-scan.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-bridge-hole-scan.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-bridge-set.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-bridge-set.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-cache-monitor.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-cache-monitor.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-chain-isolation-monitor.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-chain-isolation-monitor.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-env-watch.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-env-watch.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-escrow-residue.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-escrow-residue.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-escrow-settlements.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-escrow-settlements.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-hub-watch-deadman.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-hub-watch-deadman.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-island-subscription-check.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-island-subscription-check.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-island-swarm-probe.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-island-swarm-probe.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-journal-errors.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-journal-errors.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-memory-monitor.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-memory-monitor.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-native-energy-rate-refresh.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-native-energy-rate-refresh.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-ntfy-bridge.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-ntfy-heartbeat-daily.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-ntfy-heartbeat-daily.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-ntfy-heartbeat-hourly.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/monitoring/aitbc-ntfy-heartbeat-hourly.timer` | `scripts/monitoring` | OPS | yes | timer activation unit; service pair expected |
| `scripts/monitoring/aitbc-prometheus-watch.service` | `scripts/monitoring` | OPS | yes | monitoring unit; moves with OPS unless explicitly reclassified |
| `scripts/ops/offsite-pull-backups.service` | `scripts/ops` | OPS | no | offsite backup aggregation unit |
| `scripts/ops/offsite-pull-backups.timer` | `scripts/ops` | OPS | no | timer activation unit; service pair expected |
| `scripts/security/aitbc-security-nightly.service` | `scripts/security` | OPS | yes | nightly security unit |
| `scripts/security/aitbc-security-nightly.timer` | `scripts/security` | OPS | yes | timer activation unit; service pair expected |
| `scripts/utils/aitbc-load-secrets.service` | `scripts/utils` | PRODUCT | yes | infrastructure unit always linked by link-systemd role model |
| `scripts/utils/aitbc-recovery.service` | `scripts/utils` | PRODUCT | yes | infrastructure unit always linked by link-systemd role model |

## Pre-commit hook survival inventory

All local hook entries resolve to PRODUCT or DEV-INFRA paths and therefore survive on the product side. The single cross-tree oddity is already ruled: `website-asset-stamp` invokes `scripts/ci/check-website-stamp.sh`, which in turn expects the PRODUCT-classified `scripts/ops/stamp-website-assets.py` to relocate to `scripts/ci`. External upstream hooks are unaffected by the split.

| hook id | repo | entry | survives PRODUCT-side? | resolution |
|---|---|---|---|---|
| `trailing-whitespace` | `https://github.com/pre-commit/pre-commit-hooks` | `(upstream default)` | yes | external upstream hook repo https://github.com/pre-commit/pre-commit-hooks |
| `end-of-file-fixer` | `https://github.com/pre-commit/pre-commit-hooks` | `(upstream default)` | yes | external upstream hook repo https://github.com/pre-commit/pre-commit-hooks |
| `check-yaml` | `https://github.com/pre-commit/pre-commit-hooks` | `(upstream default)` | yes | external upstream hook repo https://github.com/pre-commit/pre-commit-hooks |
| `check-added-large-files` | `https://github.com/pre-commit/pre-commit-hooks` | `(upstream default)` | yes | external upstream hook repo https://github.com/pre-commit/pre-commit-hooks |
| `check-json` | `https://github.com/pre-commit/pre-commit-hooks` | `(upstream default)` | yes | external upstream hook repo https://github.com/pre-commit/pre-commit-hooks |
| `debug-statements` | `https://github.com/pre-commit/pre-commit-hooks` | `(upstream default)` | yes | external upstream hook repo https://github.com/pre-commit/pre-commit-hooks |
| `check-toml` | `https://github.com/pre-commit/pre-commit-hooks` | `(upstream default)` | yes | external upstream hook repo https://github.com/pre-commit/pre-commit-hooks |
| `check-xml` | `https://github.com/pre-commit/pre-commit-hooks` | `(upstream default)` | yes | external upstream hook repo https://github.com/pre-commit/pre-commit-hooks |
| `check-case-conflict` | `https://github.com/pre-commit/pre-commit-hooks` | `(upstream default)` | yes | external upstream hook repo https://github.com/pre-commit/pre-commit-hooks |
| `ruff` | `https://github.com/astral-sh/ruff-pre-commit` | `(upstream default)` | yes | external upstream hook repo https://github.com/astral-sh/ruff-pre-commit |
| `ruff-format` | `https://github.com/astral-sh/ruff-pre-commit` | `(upstream default)` | yes | external upstream hook repo https://github.com/astral-sh/ruff-pre-commit |
| `mypy-apps` | `local` | `bash scripts/ci/mypy-precommit.sh` | yes | scripts/ci/mypy-precommit.sh (DEV-INFRA) |
| `check-merge-markers` | `local` | `python3 scripts/ci/check-merge-markers.py` | yes | scripts/ci/check-merge-markers.py (DEV-INFRA) |
| `shell-strict-mode` | `local` | `python3 scripts/ci/check-shell-strict-mode.py` | yes | scripts/ci/check-shell-strict-mode.py (DEV-INFRA) |
| `check-package-managers` | `local` | `python3 scripts/ci/check-package-managers.py` | yes | scripts/ci/check-package-managers.py (DEV-INFRA) |
| `validate-docs` | `local` | `bash scripts/validate_docs.sh` | yes | scripts/validate_docs.sh (DEV-INFRA) |
| `check-master-index` | `local` | `python3 scripts/docs/gen_master_index.py --check` | yes | scripts/docs/gen_master_index.py (DEV-INFRA) |
| `check-orphan-docs` | `local` | `python3 scripts/docs/check_orphan_docs.py` | yes | scripts/docs/check_orphan_docs.py (DEV-INFRA) |
| `check-docs-path-refs` | `local` | `python3 scripts/docs/check_docs_path_refs.py` | yes | scripts/docs/check_docs_path_refs.py (DEV-INFRA) |
| `check-zk-circuit-sync` | `local` | `scripts/ci/check-zk-circuit-sync.sh` | yes | scripts/ci/check-zk-circuit-sync.sh (DEV-INFRA) |
| `check-feature-status` | `local` | `python3 scripts/docs/check_feature_status.py` | yes | scripts/docs/check_feature_status.py (DEV-INFRA) |
| `check-doc-ports` | `local` | `python3 scripts/docs/check_ports.py` | yes | scripts/docs/check_ports.py (DEV-INFRA) |
| `check-bind-policy` | `local` | `python3 scripts/docs/check_bind_policy.py` | yes | scripts/docs/check_bind_policy.py (DEV-INFRA) |
| `check-cli-docs` | `local` | `bash scripts/ci/check-cli-docs.sh` | yes | scripts/ci/check-cli-docs.sh (DEV-INFRA) |
| `check-type-ignores` | `local` | `bash scripts/ci/check-type-ignores.sh` | yes | scripts/ci/check-type-ignores.sh (DEV-INFRA) |
| `no-float-money` | `local` | `python3 scripts/lint/no_float_money.py` | yes | scripts/lint/no_float_money.py (DEV-INFRA) |
| `no-orphan-modules` | `local` | `python3 scripts/lint/no_orphan_modules.py` | yes | scripts/lint/no_orphan_modules.py (DEV-INFRA) |
| `mcp-cli-drift` | `local` | `bash scripts/ci/check-mcp-cli-drift.sh` | yes | scripts/ci/check-mcp-cli-drift.sh (DEV-INFRA) |
| `website-asset-stamp` | `local` | `bash scripts/ci/check-website-stamp.sh` | yes | scripts/ci/check-website-stamp.sh (DEV-INFRA); requires ops/stamp-website-assets.py relocation to scripts/ci per ruling |
| `openapi-drift` | `local` | `bash scripts/ci/check-openapi-drift.sh` | yes | scripts/ci/check-openapi-drift.sh (DEV-INFRA) |
| `bandit` | `https://github.com/PyCQA/bandit` | `(upstream default)` | yes | external upstream hook repo https://github.com/PyCQA/bandit |
| `c901-ratchet` | `local` | `bash scripts/ci/check-c901-ratchet.sh` | yes | scripts/ci/check-c901-ratchet.sh (DEV-INFRA) |
| `except-ratchet` | `local` | `bash scripts/ci/check-except-ratchet.sh` | yes | scripts/ci/check-except-ratchet.sh (DEV-INFRA) |
| `module-size-ratchet` | `local` | `python3 scripts/ci/check-module-size.py` | yes | scripts/ci/check-module-size.py (DEV-INFRA) |
| `critical-path-tests` | `local` | `bash scripts/ci/check-critical-path-tests.sh` | yes | scripts/ci/check-critical-path-tests.sh (DEV-INFRA) |
| `assert-print-ratchet` | `local` | `python3 scripts/check_no_assert_print.py` | yes | scripts/check_no_assert_print.py (DEV-INFRA) |
| `fake-async-ratchet` | `local` | `python3 scripts/ci/check-fake-async.py` | yes | scripts/ci/check-fake-async.py (DEV-INFRA) |
| `unawaited-async-ratchet` | `local` | `python3 scripts/ci/check-unawaited-async.py` | yes | scripts/ci/check-unawaited-async.py (DEV-INFRA) |

## Static `/opt/aitbc/scripts` references

Static tracked-file scan found **207 lines** containing the literal `/opt/aitbc/scripts`. This is not a live fleet/crontab probe; it is the complete static literal inventory inferable from the checkout, including symlink-target content for tracked symlinks (notably root `health-check.sh`). Generated docs may amplify the same logical reference.

- `apps/blockchain-node/src/aitbc_chain/sync_divergence.py:67` — `"\`sudo CHAIN_ID=%s /opt/aitbc/scripts/ops/reset-follower-to-snapshot.sh\` (or the legacy "`
- `cli/aitbc_cli/commands/control.py:21` — `HEALTH_CHECK_SCRIPT = "/opt/aitbc/scripts/monitoring/health_check.sh"`
- `cli/aitbc_cli/commands/script.py:16` — `aitbc script run --script-path /opt/aitbc/scripts/setup.sh"""`
- `cli/aitbc_cli/commands/script.py:26` — `aitbc script run --script-path /opt/aitbc/scripts/setup.sh`
- `cli/aitbc_cli/commands/script.py:28` — `aitbc script run --script-path /opt/aitbc/scripts/setup.sh --args '--verbose'"""`
- `cli/aitbc_cli/commands/script.py:81` — `aitbc script list --script-dir /opt/aitbc/scripts"""`
- `cli/aitbc_cli/commands/script.py:83` — `@click.option("--script-dir", default="/opt/aitbc/scripts", help="Scripts directory")`
- `cli/aitbc_cli/commands/system.py:1505` — `"/opt/aitbc/scripts/",`
- `cli/aitbc_cli/commands/system.py:1530` — `aitbc system run-script --path /opt/aitbc/scripts/maintenance/backup.sh""",`
- `docs/agent/guides/open-island-joining-guide.md:176` — `/opt/aitbc/scripts/utils/link-systemd.sh`
- `docs/archive/reference/8_blockchain-deployment-summary.md:163` — `- \`/opt/aitbc/scripts/deployment/deploy-first-node.sh\``
- `docs/archive/reference/8_blockchain-deployment-summary.md:164` — `- \`/opt/aitbc/scripts/deployment/deploy-second-node.sh\``
- `docs/archive/reference/8_blockchain-deployment-summary.md:165` — `- \`/opt/aitbc/scripts/deployment/setup-gossip-relay.sh\``
- `docs/archive/security/SECURITY_FIXES_SUMMARY.md:131` — `- **Updated /opt/aitbc/scripts/deployment/setup.sh**:`
- `docs/archive/security/SECURITY_FIXES_SUMMARY.md:136` — `- **Updated /opt/aitbc/scripts/utils/setup_production.py**:`
- `docs/cli/commands/script-list.md:17` — `| \`--script-dir\` | text | \`/opt/aitbc/scripts\` | no | Scripts directory |`
- `docs/cli/permission-setup.md:38` — `/opt/aitbc/scripts/clean-permissions-fix.sh`
- `docs/cli/permission-setup.md:41` — `/opt/aitbc/scripts/test-permissions.sh`
- `docs/cli/permission-setup.md:126` — `/opt/aitbc/scripts/dev-services.sh`
- `docs/cli/permission-setup.md:141` — `/opt/aitbc/scripts/fix-permissions.sh`
- `docs/cli/permission-setup.md:151` — `/opt/aitbc/scripts/test-permissions.sh`
- `docs/cli/permission-setup.md:154` — `/opt/aitbc/scripts/test-permissions.sh # Run all tests`
- `docs/cli/permission-setup.md:165` — `/opt/aitbc/scripts/fix-permissions.sh`
- `docs/cli/permission-setup.md:282` — `/opt/aitbc/scripts/test-permissions.sh`
- `docs/deployment/SERVICE_USERS.md:158` — `sudo cp /opt/aitbc/scripts/deployment/aitbc-logrotate.conf /etc/logrotate.d/aitbc`
- `docs/deployment/bc2-consumers.md:69` — `\`/opt/aitbc/scripts/maintenance/aitbc-backup.sh\`. The env file exists on`
- `docs/development/workspace/WORKSPACE_STRATEGY.md:119` — `# /opt/aitbc/scripts/setup-workspace.sh`
- `docs/getting-started/SETUP.md:8` — `> **⚠️ v0.4.26 Update**: JWT authentication is now required. \`setup.sh\` automatically generates \`JWT_SECRET\` and \`SECRET_KEY\`. If upgrading from an earlier version, run \`/opt/aitbc/scripts/utils/load-keystore-secrets....`
- `docs/getting-started/SETUP.md:87` — `/opt/aitbc/scripts/dump_mcp_tools.py --role <role> --output mcp-tools.md`
- `docs/getting-started/SETUP.md:101` — `sudo /opt/aitbc/scripts/deployment/setup.sh \`
- `docs/getting-started/UPDATE.md:12` — `> sudo /opt/aitbc/scripts/deployment/update.sh`
- `docs/getting-started/UPDATE.md:20` — `/opt/aitbc/scripts/dump_mcp_tools.py --role <role> --output mcp-tools.md`
- `docs/getting-started/UPDATE.md:43` — `sudo /opt/aitbc/scripts/deployment/update.sh`
- `docs/getting-started/UPDATE.md:74` — `sudo /opt/aitbc/scripts/deployment/update.sh --no-pull`
- `docs/getting-started/UPDATE.md:77` — `sudo /opt/aitbc/scripts/deployment/update.sh --no-restart`
- `docs/getting-started/UPDATE.md:80` — `sudo /opt/aitbc/scripts/deployment/update.sh --no-pull --skip-backup`
- `docs/getting-started/UPDATE.md:83` — `sudo /opt/aitbc/scripts/deployment/update.sh --no-migrate`
- `docs/getting-started/UPDATE.md:125` — `sudo /opt/aitbc/scripts/deployment/update.sh --gitea`
- `docs/getting-started/UPDATE.md:127` — `sudo /opt/aitbc/scripts/deployment/update.sh --gitea http://gitea.example.com/oib/aitbc.git`
- `docs/getting-started/UPDATE.md:129` — `sudo AITBC_GIT_REMOTE=https://gitea.invalid/oib/AITBC.git /opt/aitbc/scripts/deployment/update.sh`
- `docs/getting-started/UPDATE.md:346` — `sudo /opt/aitbc/scripts/deployment/update.sh --gitea`
- `docs/getting-started/UPDATE.md:348` — `sudo /opt/aitbc/scripts/deployment/update.sh --remote http://your-mirror/oib/aitbc.git`
- `docs/getting-started/UPDATE.md:372` — `sudo /opt/aitbc/scripts/deployment/update.sh --no-pull`
- `docs/getting-started/installation/quick-start.md:71` — `/opt/aitbc/scripts/monitoring/health_check.sh`
- `docs/getting-started/overview/cli-guide.md:37` — `/opt/aitbc/scripts/clean-permissions-fix.sh`
- `docs/getting-started/overview/cli-guide.md:40` — `/opt/aitbc/scripts/test-permissions.sh`
- `docs/getting-started/overview/cli-guide.md:50` — `/opt/aitbc/scripts/utils/check-dependencies.sh`
- `docs/getting-started/overview/cli-guide.md:120` — `/opt/aitbc/scripts/fix-permissions.sh`
- `docs/getting-started/overview/cli-guide.md:123` — `/opt/aitbc/scripts/test-permissions.sh`
- `docs/getting-started/overview/cli-guide.md:149` — `/opt/aitbc/scripts/utils/check-dependencies.sh`
- `docs/getting-started/overview/introduction.md:54` — `sudo /opt/aitbc/scripts/deployment/setup.sh \`
- `docs/getting-started/reference/management-commands.md:7` — `/opt/aitbc/scripts/monitoring/health_check.sh`
- `docs/getting-started/setup-configuration.md:45` — `sudo /opt/aitbc/scripts/deployment/setup.sh`
- `docs/getting-started/setup-configuration.md:50` — `sudo /opt/aitbc/scripts/utils/load-keystore-secrets.sh`
- `docs/getting-started/setup-configuration.md:89` — `sudo /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh`
- `docs/getting-started/setup-configuration.md:118` — `sudo /opt/aitbc/scripts/utils/load-keystore-secrets.sh`
- `docs/getting-started/setup-reference.md:110` — `/opt/aitbc/scripts/monitoring/health_check.sh`
- `docs/getting-started/setup-reference.md:135` — `sudo /opt/aitbc/scripts/deployment/update.sh`
- `docs/getting-started/setup-reference.md:147` — `sudo /opt/aitbc/scripts/deployment/setup.sh --force`
- `docs/getting-started/setup-reference.md:239` — `sudo /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh`
- `docs/getting-started/setup-reference.md:257` — `sudo /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh`
- `docs/getting-started/setup-service-selection.md:175` — `sudo /opt/aitbc/scripts/maintenance/aitbc-backup.sh`
- `docs/infrastructure/README.md:119` — `/opt/aitbc/scripts/monitoring/health_check.sh`
- `docs/infrastructure/VIRTUAL_ENVIRONMENT.md:32` — `/opt/aitbc/scripts/aitbc-cli --help`
- `docs/infrastructure/VIRTUAL_ENVIRONMENT.md:39` — `/opt/aitbc/scripts/aitbc-cli --help`
- `docs/infrastructure/monitoring-setup.md:167` — `sudo ln -sfn /opt/aitbc/scripts/monitoring/aitbc-journal-errors.{service,timer} /etc/systemd/system/`
- `docs/infrastructure/monitoring-setup.md:184` — `sudo ln -sfn /opt/aitbc/scripts/monitoring/aitbc-env-watch.{service,timer} /etc/systemd/system/`
- `docs/infrastructure/monitoring-setup.md:370` — `sudo ln -sfn /opt/aitbc/scripts/monitoring/aitbc-attestation-arrival.{service,timer} /etc/systemd/system/`
- `docs/infrastructure/monitoring-setup.md:383` — `sudo ln -sfn /opt/aitbc/scripts/monitoring/aitbc-island-swarm-probe.{service,timer} /etc/systemd/system/`
- `docs/ops/backup-assurance.md:27` — `sudo install -m644 /opt/aitbc/scripts/maintenance/aitbc-backup-verify.{service,timer} /etc/systemd/system/`
- `docs/ops/backup-restore.md:167` — `cp /opt/aitbc/scripts/ops/offsite-pull-backups.{service,timer} ~/.config/systemd/user/`
- `docs/ops/native-energy-rate-guard-deploy.md:19` — `| \`scripts/monitoring/native-energy-rate-refresh.sh\` | hub only | runs in place — the unit \`ExecStart\`s \`/opt/aitbc/scripts/monitoring/native-energy-rate-refresh.sh\` (#1729; the \`/usr/local/sbin\` copy is no longer use...`
- `docs/reference/1_cli-reference.md:214` — `aitbc script list [--script-dir /opt/aitbc/scripts]`
- `docs/reference/all-routes.md:6` — `> /opt/aitbc/venv/bin/python /opt/aitbc/scripts/docs/gen_all_routes.py \`
- `docs/releases/2026/versions/v0.10/v0.10.18_AGENTS.md:91` — `/opt/aitbc/scripts/monitoring/health_check.sh all`
- `docs/releases/2026/README.md#v01018` — `/opt/aitbc/scripts/monitoring/health_check.sh all`
- `docs/releases/2026/README.md#v023` — `sudo /opt/aitbc/scripts/deployment/run-migrations.sh`
- `docs/releases/2026/README.md#v023` — `\`cat >\` into \`/opt/aitbc/scripts/health-check.sh\`, untracked, inside the git checkout, and`
- `docs/releases/2026/README.md#v02334` — `sudo /opt/aitbc/scripts/deployment/run-migrations.sh`
- `docs/releases/2026/README.md#v02334` — `\`cat >\` into \`/opt/aitbc/scripts/health-check.sh\`, untracked, inside the git checkout, and`
- `docs/releases/2026/README.md#v045` — `/opt/aitbc/scripts/setup/install-nginx-node.sh`
- `docs/releases/2026/README.md#v0426` — `**Problem**: \`aitbc-recovery.service\` ends with \`|| true\`, so secret-loading or relinking failures always report success to systemd. <ref_snippet file="/opt/aitbc/scripts/systemd/aitbc-recovery.service" lines="8" />`
- `docs/releases/2026/versions/v0.4/v0.4.7_PLUGIN_SERVICE_MIGRATION.md:45` — `Migration script at \`/opt/aitbc/scripts/migration/migrate_plugin_to_marketplace.py\`:`
- `docs/releases/2026/versions/v0.5/v0.5.0_systemd-hardening-report.md:649` — `Path: \`/opt/aitbc/scripts/monitoring/aitbc-monitoring.service\``
- `docs/releases/2026/versions/v0.5/v0.5.0_systemd-hardening-report.md:673` — `Path: \`/opt/aitbc/scripts/systemd/aitbc-recovery.service\``
- `docs/releases/2026/versions/v0.5/v0.5.0_systemd-hardening-report.md:698` — `Path: \`/opt/aitbc/scripts/utils/aitbc-load-secrets.service\``
- `docs/releases/2026/versions/v0.5/v0.5.0_systemd-hardening-report.md:718` — `Path: \`/opt/aitbc/scripts/utils/aitbc-plugin.service\``
- `docs/releases/2026/README.md#v0510` — `python3 /opt/aitbc/scripts/migration/scale_balances_3600x.py`
- `docs/releases/2026/versions/v0.5/v0.5.10_migrate-hub.md:82` — `test -f /opt/aitbc/scripts/migration/scale_balances_3600x.py && echo "OK: migration script" || echo "MISSING: migration script"`
- `docs/releases/2026/versions/v0.5/v0.5.10_migrate-hub.md:83` — `test -x /opt/aitbc/scripts/migration/scale_balances_3600x.py && echo "OK: executable" || echo "NOT EXECUTABLE"`
- `docs/releases/2026/versions/v0.5/v0.5.10_pre-flight-checks.md:18` — `test -f /opt/aitbc/scripts/migration/scale_balances_3600x.py && echo "OK: migration script" || echo "MISSING: migration script"`
- `docs/releases/2026/versions/v0.5/v0.5.10_pre-flight-checks.md:19` — `test -x /opt/aitbc/scripts/migration/scale_balances_3600x.py && echo "OK: executable" || echo "NOT EXECUTABLE"`
- `docs/releases/2026/versions/v0.5/v0.5.11_AGENTS.md:264` — `- **Problem**: Service file at \`/opt/aitbc/scripts/utils/aitbc-recovery.service\` not symlinked into \`/etc/systemd/system/\`.`
- `docs/releases/2026/versions/v0.5/v0.5.11_AGENTS.md:265` — `- **Fix**: \`ln -s /opt/aitbc/scripts/utils/aitbc-recovery.service /etc/systemd/system/aitbc-recovery.service && systemctl daemon-reload\``
- `docs/releases/2026/versions/v0.5/v0.5.11_agent-b.md:64` — `- **Problem**: Service file at \`/opt/aitbc/scripts/utils/aitbc-recovery.service\` not symlinked into \`/etc/systemd/system/\`.`
- `docs/releases/2026/versions/v0.5/v0.5.11_agent-b.md:65` — `- **Fix**: Create symlink: \`sudo ln -s /opt/aitbc/scripts/utils/aitbc-recovery.service /etc/systemd/system/aitbc-recovery.service\`.`
- `docs/releases/2026/README.md#v0511` — `**Problem:** The service file exists at \`/opt/aitbc/scripts/utils/aitbc-recovery.service\` but was not symlinked into \`/etc/systemd/system/\`. Systemd showed \`Loaded: not-found\` despite the service being active.`
- `docs/releases/2026/README.md#v0511` — `/etc/systemd/system/aitbc-recovery.service → /opt/aitbc/scripts/utils/aitbc-recovery.service`
- `docs/scenarios/27_cli_commands.md:50` — `- AITBC CLI (\`aitbc\`) on \`$PATH\` — not \`/opt/aitbc/scripts/aitbc-cli\``
- `docs/scenarios/59_sepolia_buy_sell_ait.md:488` — `ssh hub 'venv/bin/python /opt/aitbc/scripts/ops/exchange_verify.py \`
- `docs/scenarios/70_script_runner.md:52` — `\`/opt/aitbc/scripts\`)`
- `docs/scenarios/70_script_runner.md:62` — `aitbc script list --script-dir /opt/aitbc/scripts`
- `docs/scenarios/70_script_runner.md:74` — `aitbc script run --script-path /opt/aitbc/scripts/monitoring/fleet-config-check.sh`
- `docs/testing/e2e-test-scenarios.md:35` — `**Scenario Scripts Location:** \`/opt/aitbc/scripts/workflow/\` (the \`dev/testing/\` tree was retired from the repo 2026-09-28)`
- `health-check.sh:1` — `SYMLINK -> /opt/aitbc/scripts/monitoring/health_check.sh`
- `mcp-server/README.md:366` — `* \`run_cron_job\` only accepts scripts under \`/opt/aitbc/scripts/\`,`
- `mcp-server/tests/test_aitbc_mcp_path_args.py:32` — `"/opt/aitbc/scripts/../../tmp/x.sh",`
- `mcp-server/tests/test_aitbc_mcp_path_args.py:56` — `"/opt/aitbc/scripts/../../tmp/x.sh",`
- `scripts/deployment/deploy/deploy-domain.sh:34` — `python3 /opt/aitbc/scripts/deployment/deploy/container-deploy.py`
- `scripts/deployment/run-migrations.sh:27` — `# sudo /opt/aitbc/scripts/deployment/run-migrations.sh`
- `scripts/deployment/run-migrations.sh:28` — `# sudo AITBC_ROOT=/opt/aitbc /opt/aitbc/scripts/deployment/run-migrations.sh`
- `scripts/deployment/update.sh:24` — `# sudo /opt/aitbc/scripts/deployment/update.sh`
- `scripts/deployment/update.sh:25` — `# sudo /opt/aitbc/scripts/deployment/update.sh --no-pull # skip git pull`
- `scripts/deployment/update.sh:26` — `# sudo /opt/aitbc/scripts/deployment/update.sh --no-restart # skip service restart`
- `scripts/deployment/update.sh:27` — `# sudo /opt/aitbc/scripts/deployment/update.sh --no-migrate # skip DB migrations`
- `scripts/deployment/update.sh:28` — `# sudo /opt/aitbc/scripts/deployment/update.sh --skip-backup # skip pre-update backup`
- `scripts/deployment/update.sh:29` — `# sudo /opt/aitbc/scripts/deployment/update.sh --gitea # pull from the canonical Gitea repo`
- `scripts/deployment/update.sh:30` — `# sudo /opt/aitbc/scripts/deployment/update.sh --remote URL # override git remote`
- `scripts/maintenance/aitbc-backup-verify.service:19` — `ExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/scripts/ops/backup-verify.py --textfile /var/lib/prometheus/node-exporter/aitbc_backup_verify.prom`
- `scripts/maintenance/aitbc-backup.service:17` — `ExecStart=/opt/aitbc/scripts/maintenance/aitbc-backup.sh`
- `scripts/maintenance/aitbc-backup.sh:567` — `if PYTHONPATH="/opt/aitbc" "$PYTHON" /opt/aitbc/scripts/ops/key-audit.py --report "${BACKUP_DIR}/key-audit.json"; then`
- `scripts/monitoring/aitbc-alert-digest.service:15` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/alert-digest.py`
- `scripts/monitoring/aitbc-attestation-arrival.service:23` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/attestation-arrival-textfile.py`
- `scripts/monitoring/aitbc-authority-balances.service:23` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/authority-balances-textfile.py`
- `scripts/monitoring/aitbc-backup-metrics.service:18` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/backup-textfile.py`
- `scripts/monitoring/aitbc-bridge-hole-scan.service:15` — `ExecStart=/opt/aitbc/scripts/monitoring/bridge-header-hole-scan.sh`
- `scripts/monitoring/aitbc-bridge-set.service:30` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/bridge-set-textfile.py`
- `scripts/monitoring/aitbc-cache-monitor.service:20` — `ExecStart=/opt/aitbc/scripts/monitoring/cache-monitor.sh`
- `scripts/monitoring/aitbc-chain-isolation-monitor.service:12` — `ExecStart=/opt/aitbc/scripts/monitoring/verify_chain_isolation.sh`
- `scripts/monitoring/aitbc-env-watch.service:20` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/env-watch-textfile.py`
- `scripts/monitoring/aitbc-escrow-residue.service:16` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/escrow-residue-textfile.py`
- `scripts/monitoring/aitbc-escrow-settlements.service:17` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/escrow-settlements-textfile.py`
- `scripts/monitoring/aitbc-hub-watch-deadman.service:14` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/hub-watch-deadman-textfile.py`
- `scripts/monitoring/aitbc-island-subscription-check.service:16` — `ExecStart=/opt/aitbc/scripts/monitoring/island-subscription-check.sh`
- `scripts/monitoring/aitbc-island-swarm-probe.service:22` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/island-swarm-probe-textfile.py`
- `scripts/monitoring/aitbc-journal-errors.service:15` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/journal-errors-textfile.py`
- `scripts/monitoring/aitbc-memory-monitor.service:13` — `ExecStart=/opt/aitbc/scripts/monitoring/memory-monitor.sh`
- `scripts/monitoring/aitbc-native-energy-rate-refresh.service:13` — `ExecStart=/opt/aitbc/scripts/monitoring/native-energy-rate-refresh.sh`
- `scripts/monitoring/aitbc-ntfy-bridge.service:17` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/ntfy-alert-bridge.py`
- `scripts/monitoring/aitbc-ntfy-heartbeat-daily.service:13` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/ntfy-heartbeat.py --kind daily`
- `scripts/monitoring/aitbc-ntfy-heartbeat-hourly.service:17` — `ExecStart=/usr/bin/python3 /opt/aitbc/scripts/monitoring/ntfy-heartbeat.py --kind hourly`
- `scripts/monitoring/aitbc_rules_test.yml:780` — `- series: 'aitbc_escrow_settlement_scrape_success{db="/opt/aitbc/scripts/monitoring/escrow-known-artifacts.yml", instance="n:9100"}'`
- `scripts/monitoring/aitbc_rules_test.yml:789` — `- labels: 'ALERTS{alertname="EscrowSettlementCheckFailed", alertstate="firing", db="/opt/aitbc/scripts/monitoring/escrow-known-artifacts.yml", instance="n:9100", severity="warning"}'`
- `scripts/ops/fix-x-forwarded-proto.sh:9` — `# ssh hub 'sh /opt/aitbc/scripts/ops/fix-x-forwarded-proto.sh' # dry-run report`
- `scripts/ops/fix-x-forwarded-proto.sh:10` — `# ssh hub 'sh /opt/aitbc/scripts/ops/fix-x-forwarded-proto.sh --apply' # fix + reload`
- `scripts/ops/offsite-pull-backups.service:11` — `ExecStart=/opt/aitbc/scripts/ops/offsite-pull-backups.sh`
- `scripts/ops/register_bridge_validators.py:15` — `python3 /opt/aitbc/scripts/ops/register_bridge_validators.py \`
- `scripts/ops/render-bootstrap-env.sh:12` — `# bash /opt/aitbc/scripts/ops/render-bootstrap-env.sh`
- `scripts/ops/render-website.sh:29` — `# bash /opt/aitbc/scripts/ops/render-website.sh`
- `scripts/ops/reset-follower-to-snapshot.sh:9` — `# sudo bash /opt/aitbc/scripts/ops/reset-follower-to-snapshot.sh`
- `scripts/security/aitbc-security-nightly.service:21` — `ExecStart=/bin/bash /opt/aitbc/scripts/security/nightly-security.sh`
- `scripts/services/gpu/miner.spec:7` — `pathex=['/opt/aitbc/scripts/services/gpu'],`
- `scripts/setup/install-nginx-node.sh:6` — `# Usage: sudo bash /opt/aitbc/scripts/setup/install-nginx-node.sh`
- `scripts/setup/install-system-deps.sh:7` — `# /opt/aitbc/scripts/setup/install-system-deps.sh # dry-run / check only`
- `scripts/setup/install-system-deps.sh:8` — `# sudo /opt/aitbc/scripts/setup/install-system-deps.sh --install`
- `scripts/setup/install-system-deps.sh:9` — `# sudo /opt/aitbc/scripts/setup/install-system-deps.sh --install --build --npm`
- `scripts/utils/aitbc-load-secrets.service:15` — `ExecStart=/opt/aitbc/scripts/utils/load-keystore-secrets.sh`
- `scripts/utils/aitbc-recovery.service:10` — `ExecStart=/bin/bash -c '/opt/aitbc/scripts/utils/link-systemd.sh && /opt/aitbc/scripts/utils/load-keystore-secrets.sh'`
- `scripts/utils/common.sh:6` — `# Source this file in other scripts: source /opt/aitbc/scripts/utils/common.sh`
- `scripts/utils/env_config.sh:6` — `# Source this file: source /opt/aitbc/scripts/utils/env_config.sh`
- `scripts/utils/security_hardening.sh:244` — `local health_check="/opt/aitbc/scripts/monitoring/health_check.sh"`
- `scripts/utils/security_hardening.sh:294` — `mkdir -p /opt/aitbc/scripts`
- `scripts/workflow/02_genesis_authority_setup.sh:63` — `/opt/aitbc/scripts/deployment/setup_postgresql_databases.sh`
- `scripts/workflow/03_follower_node_setup.sh:68` — `/opt/aitbc/scripts/deployment/setup_postgresql_databases.sh`
- `scripts/workflow/16_monitoring_setup.sh:25` — `cat > /opt/aitbc/scripts/health_check.sh << 'EOF'`
- `scripts/workflow/16_monitoring_setup.sh:102` — `chmod +x /opt/aitbc/scripts/health_check.sh`
- `scripts/workflow/16_monitoring_setup.sh:106` — `(crontab -l 2>/dev/null | grep -vF '/opt/aitbc/scripts/health_check.sh'; echo "*/5 * * * * /opt/aitbc/scripts/health_check.sh") | crontab -`
- `scripts/workflow/16_monitoring_setup.sh:135` — `cat > /opt/aitbc/scripts/monitoring_dashboard.sh << 'EOF'`
- `scripts/workflow/16_monitoring_setup.sh:184` — `chmod +x /opt/aitbc/scripts/monitoring_dashboard.sh`
- `scripts/workflow/16_monitoring_setup.sh:188` — `scp /opt/aitbc/scripts/health_check.sh aitbc:/opt/aitbc/scripts/`
- `scripts/workflow/16_monitoring_setup.sh:189` — `scp /opt/aitbc/scripts/monitoring_dashboard.sh aitbc:/opt/aitbc/scripts/`
- `scripts/workflow/16_monitoring_setup.sh:190` — `ssh aitbc 'chmod +x /opt/aitbc/scripts/health_check.sh /opt/aitbc/scripts/monitoring_dashboard.sh'`
- `scripts/workflow/16_monitoring_setup.sh:193` — `ssh aitbc "(crontab -l 2>/dev/null | grep -vF '/opt/aitbc/scripts/health_check.sh'; echo '*/5 * * * * /opt/aitbc/scripts/health_check.sh') | crontab -"`
- `scripts/workflow/17_security_hardening.sh:91` — `cat > /opt/aitbc/scripts/security_monitor.sh << 'EOF'`
- `scripts/workflow/17_security_hardening.sh:143` — `chmod +x /opt/aitbc/scripts/security_monitor.sh`
- `scripts/workflow/17_security_hardening.sh:146` — `(crontab -l 2>/dev/null; echo "0 * * * * /opt/aitbc/scripts/security_monitor.sh") | crontab -`
- `scripts/workflow/17_security_hardening.sh:150` — `scp /opt/aitbc/scripts/security_monitor.sh aitbc:/opt/aitbc/scripts/`
- `scripts/workflow/21_maintenance_automation.sh:185` — `if [ -f "/opt/aitbc/scripts/security_monitor.sh" ]; then`
- `scripts/workflow/21_maintenance_automation.sh:187` — `/opt/aitbc/scripts/security_monitor.sh >/dev/null 2>&1 || true`
- `scripts/workflow/23_scaling_preparation.sh:459` — `/opt/aitbc/scripts/workflow/03_follower_node_setup.sh`
- `scripts/workflow/27_operations_automation.sh:119` — `ssh aitbc '/opt/aitbc/scripts/fast_bulk_sync.sh'`
- `scripts/workflow/31_consensus_testing.sh:328` — `echo "- Command: /opt/aitbc/scripts/fast_bulk_sync.sh" >> "$DEBUG_REPORT"`
- `scripts/workflow/41_complete_optimization_workflow.sh:93` — `/opt/aitbc/scripts/workflow/34_service_health_monitoring.sh quick`
- `scripts/workflow/41_complete_optimization_workflow.sh:115` — `/opt/aitbc/scripts/workflow/39_agent_communication_testing.sh | head -20`
- `scripts/workflow/41_complete_optimization_workflow.sh:125` — `/opt/aitbc/scripts/workflow/36_contract_security_testing.sh | head -20`
- `scripts/workflow/41_complete_optimization_workflow.sh:135` — `/opt/aitbc/scripts/workflow/37_contract_event_monitoring.sh | head -20`
- `scripts/workflow/41_complete_optimization_workflow.sh:145` — `/opt/aitbc/scripts/workflow/38_contract_data_analytics.sh | head -20`
- `scripts/workflow/README.md:90` — `/opt/aitbc/scripts/workflow/`
- `skills/aitbc-deployment/SKILL.md:54` — `bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh`
- `skills/aitbc-deployment/SKILL.md:129` — `/opt/aitbc/scripts/deployment/install-profiles.sh provider-gpu`
- `skills/aitbc-deployment/SKILL.md:136` — `- \`aitbc\` not on PATH: \`ln -sf /opt/aitbc/scripts/aitbc-cli /usr/local/bin/aitbc\``
- `skills/aitbc-node-management/SKILL.md:79` — `Then load secrets: \`bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh\``
- `skills/aitbc-node-management/SKILL.md:373` — `bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh`
- `skills/aitbc-node-management/SKILL.md:414` — `bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh`
- `skills/aitbc-service-recovery/SKILL.md:18` — `bash /opt/aitbc/scripts/utils/link-systemd.sh`
- `skills/aitbc-service-recovery/SKILL.md:24` — `bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh`
- `skills/aitbc-software-setup/SKILL.md:83` — `bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh`
- `skills/aitbc-software-setup/SKILL.md:155` — `/opt/aitbc/scripts/utils/link-systemd.sh`
- `skills/aitbc-software-setup/SKILL.md:158` — `for svc in /opt/aitbc/apps/*/aitbc-*.service /opt/aitbc/scripts/utils/aitbc-*.service \`
- `skills/aitbc-software-setup/SKILL.md:159` — `/opt/aitbc/scripts/monitoring/aitbc-*.service; do`
- `skills/aitbc-software-setup/SKILL.md:223` — `/opt/aitbc/scripts/monitoring/health_check.sh`
- `skills/aitbc/aitbc-blockchain-troubleshooting.md:144` — `/opt/aitbc/scripts/utils/generate_unique_node_ids.py`
- `skills/aitbc/aitbc-node-coordination.md:141` — `2. **P2P Handshake Rejection:** Check for duplicate p2p_node_id, run \`/opt/aitbc/scripts/utils/generate_unique_node_ids.py\``
- `tests/unit/test_authority_balances_textfile.py:500` — `assert "/opt/aitbc/scripts/monitoring/authority-balances-textfile.py" in unit`
- `tests/unit/test_escrow_settlements_textfile.py:497` — `assert "/opt/aitbc/scripts/monitoring/escrow-settlements-textfile.py" in unit`
- `tests/unit/test_sync_detector_failclosed.py:47` — `assert "/opt/aitbc/scripts/bulk_sync.sh" not in src`
- `tests/unit/test_workflow_preflight.py:208` — `assert "grep -vF '/opt/aitbc/scripts/health_check.sh'" in src`

## Open judgment calls and recommendations

- **scripts/gpu** — README-only directory. Recommendation: PRODUCT placeholder/index because GPU miner/operator docs are public product surface; no executable coupling.
- **scripts/audit** — OPS. `reconcile_agent_wallets.py` is operator financial reconciliation/audit across deployed wallets, not needed to run a node.
- **scripts/sync** — OPS. `sync_detector.sh` is fleet state-divergence detection; unit-test pin follows it into ops.
- **scripts/migration** — PRODUCT. Schema/data migration helpers are required for public node upgrades; keep with `run-migrations.sh`. Incident-specific one-offs should be renamed/annotated rather than moved wholesale.
- **scripts/performance** — DEV-INFRA. `run_load_tests.sh` is thresholded load-test engineering validation referenced by test harnesses/workflows, not required to run a node.
- **scripts/security** — mixed, as classified: public hardening/audit utilities PRODUCT; scan/mutation/dependency/nightly test orchestration DEV-INFRA; only the fleet systemd schedule pair is OPS.
- **scripts/testing fleet pins** — mixed, as classified: chaos/multi-site/memory/native-energy harnesses OPS; coldstart harness OPS because it primarily pins the OPS bridge scan, with a recommendation to duplicate the backup half product-side; link-systemd product harness stays PRODUCT but its OPS unit fixtures are a break-point to generalize.
- **scripts/agent** — PRODUCT. `register-agent.sh` is a node-local agent registration helper for a public service role; it has no exact static refs, so the alternative is retirement rather than OPS.
- **scripts/notifications** — DEV-INFRA. `config.sh` is a contract-deployment notification/API environment template, not node runtime.
- **scripts/release** — DEV-INFRA. Changelog/version release machinery belongs with engineering gates.
- **scripts/services** — mixed, as encoded: service wrapper and host miner client PRODUCT; demo/integration probes plus `miner.spec` DEV-INFRA packaging/test support.
- **scripts/quality** — DEV-INFRA. CLI help audit is engineering quality tooling.
- **scripts/workflow** — OPS. Numbered multi-node production workflow plays are legacy fleet runbooks with host/genesis coupling, not public quickstart material.
- **scripts/config** — PRODUCT. `aitbc-secrets.conf` is tmpfiles configuration installed by setup/systemd secret flow.
- **scripts/templates** — DEV-INFRA. `service-wrapper.py.j2` is an unreferenced source template for generating service wrappers.
- **scripts/ops genesis/snapshot subset** — mixed, as encoded: canonical build/alloc/verify genesis tools PRODUCT because they are the only loader-valid island-creation path; hard-fork `create-genesis-block.py` and SSH-orchestrated follower resets OPS. Snapshot manifest generation/sign/verify are PRODUCT-side generic chain artifacts, but the current reset script is OPS and the product `sync_divergence` reference must be replaced with a public snapshot-fetch flow.
- **scripts/ops bridge subset** — OPS recommendation already encoded. Bridge administration/preflight/transplant/reconciliation scripts touch operator funds and rollout state. Public bridge operators will need replacements or a documented product-safe subset in Phase 4.
- **scripts/monitoring Prometheus rule files** — OPS recommendation already encoded despite `deployment/update.sh` referencing `deploy-rules.sh`. Treat that as a deliberate XB break-point: product update must make monitoring-rule deployment optional/pluggable rather than dragging fleet monitoring into the public repo.
- **scripts/utils legacy mesh helpers** — OPS recommendation for `common.sh`/`env_config.sh` even though currently mostly test-pinned; they belong to legacy multi-node workflow machinery and are not used by product setup.

## Verification checklist

- `find scripts \( -type f -o -type l \) | wc -l` = **420** (419 regular files + 1 symlink)
- manifest classification lines inside the Per-file manifest section (`sed -n '/^## Per-file manifest/,/^## LEAK inventory/p' docs/agent/repo-split-manifest.md | grep -c '^- \`scripts/'`) = **420**
- duplicate classification check: the generator emits exactly one line per inventory path and fails if an exception path is unknown
- no live fleet probing performed; all coupling statements are static tracked-file analysis
