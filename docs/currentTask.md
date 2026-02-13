# Current Task

No active task. All recent work documented in `done.md`.

## Last Completed (2026-02-13)

### Critical Security Fixes
- ✅ Fixed hardcoded secrets (JWT, PostgreSQL credentials)
- ✅ Unified database sessions (storage.SessionDep)
- ✅ Closed authentication gaps in exchange API
- ✅ Tightened CORS defaults across all services
- ✅ Enhanced wallet encryption (Fernet, PBKDF2)
- ✅ Fixed CI import error (requests → httpx)
- ✅ Deployed to Site A (aitbc.bubuit.net)
- ✅ Site B no action needed (blockchain node only)

### Previous (2026-02-12)

- ✅ Persistent GPU marketplace (SQLModel) — see `done.md`
- ✅ CLI integration tests (24 tests) — see `done.md`
- ✅ Coordinator billing stubs (21 tests) — see `done.md`
- ✅ Documentation updated (README, roadmap, done, structure, components, files, coordinator-api)

## Test Summary

| Suite | Tests | Source |
|-------|-------|--------|
| Blockchain node | 50 | `tests/test_blockchain_nodes.py` |
| ZK integration | 8 | `tests/test_zk_integration.py` |
| CLI unit | 141 | `tests/cli/test_*.py` (9 files) |
| CLI integration | 24 | `tests/cli/test_cli_integration.py` |
| Billing | 21 | `apps/coordinator-api/tests/test_billing.py` |
| GPU marketplace | 22 | `apps/coordinator-api/tests/test_gpu_marketplace.py` |

## Environment

- **Local testnet**: localhost blockchain nodes (ports 8081, 8082)
- **Production**: `ssh aitbc-cascade` — same codebase, single environment
- **Remote node**: `ssh ns3-root` → Site C (aitbc.keisanki.net)
- See `infrastructure.md` for full topology
