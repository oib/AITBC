# v0.5.11 Type Safety Hardening — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Bug Fixes, Infrastructure & Apps)

**Scope**: Bug fixes in `apps/`, CLI path corrections, logging consolidation, environment configuration, systemd repair, and duplicate route audit.

**Working directory**: `/opt/aitbc/` (cross-cutting)

**Verification commands**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check . && ./venv/bin/python -m mypy --show-error-codes apps/coordinator-api/src apps/blockchain-node/src
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Fix Ruff errors (audit entire repo) | Medium | — | ✅ DONE (none found) |
| B2 | Audit duplicate route registrations in coordinator-api | Medium | `apps/coordinator-api/src/app/main.py` | ✅ DONE |
| B3 | Fix circuit breaker unreachable code + state manager unreachable statements | Low | `network/circuit_breaker.py` (coordination with Agent A) | ✅ DONE |
| B4 | Fix `aitbc-recovery` broken systemd symlink | Low | `/etc/systemd/system/aitbc-recovery.service` | ✅ DONE |
| B5 | **Bug:** Broken `AgentServiceBridge` import in trading + compliance agents | High | `aitbc/agent_trading/src/trading_agent.py`, `aitbc/agent_compliance/src/compliance_agent.py` | ✅ DONE |
| B6 | **Bug:** Biased/bursty read-replica routing using `hash(time.time())` | Medium | `aitbc/database/replica.py` | ✅ DONE |
| B7 | **Bug:** PoA block proposer recorded `nonce - 1` for confirmed transactions | High | `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | ✅ DONE |
| B8 | **Bug:** CLI workflow commands used non-existent API paths | High | `cli/aitbc_cli/commands/workflow.py` | ✅ DONE |
| B9 | Consolidate duplicate logging modules (`log_utils/logging.py` → re-export) | Medium | `aitbc/log_utils/logging.py`, `aitbc/log_utils/__init__.py` | ✅ DONE |
| B10 | Make `REPO_DIR` environment-sourced via `AITBC_REPO_DIR` env var | Medium | `aitbc/constants.py` | ✅ DONE |
| B11 | Add `session.rollback()` in PoA tx processing exception handler | Medium | `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | ✅ DONE |

---

## B1: Ruff audit

- Run `ruff check .` across the entire repo. Fix any errors found.
- Expected result: 0 errors (verified — none found).

---

## B2: Duplicate route registration audit

- **Problem**: `agent_router` was included twice in `apps/coordinator-api/src/app/main.py`:
  - Line 313: `app.include_router(agent_router, prefix="/v1")` → routes at `/v1/workflows`, `/v1/executions`
  - Line 378: `app.include_router(agent_router, prefix="/v1/agents")` → routes at `/v1/agents/workflows`, `/v1/agents/executions`
- **Fix**: Remove the redundant inclusion at line 313. Keep only the `/v1/agents` prefix.
- **Verify**: App starts with 378 routes and 0 duplicates.

---

## B3: Circuit breaker unreachable code

- Fix unreachable code in `aitbc/network/circuit_breaker.py` (type `open_time: datetime | None`).
- **Note**: Coordinate with Agent A's A13 task on `circuit_breaker.py` — Agent A handles the type annotation, Agent B handles the unreachable code logic. Agent A goes first.

---

## B4: aitbc-recovery systemd symlink

- **Problem**: Service file at `/opt/aitbc/scripts/utils/aitbc-recovery.service` not symlinked into `/etc/systemd/system/`.
- **Fix**: Create symlink: `sudo ln -s /opt/aitbc/scripts/utils/aitbc-recovery.service /etc/systemd/system/aitbc-recovery.service`.
- **Verify**: `systemctl status aitbc-recovery` shows the service file is found.

---

## B5: Broken AgentServiceBridge import

- **Problem**: `AgentServiceBridge` was moved to `aitbc/agent_bridge/src/agent_bridge.py` but trading and compliance agents still import from the old path.
- **Fix**: Update imports in `agent_trading/src/trading_agent.py` and `agent_compliance/src/compliance_agent.py` to use the new path.
- **Verify**: `python -m pytest tests/unit/test_agent_trading.py` and `tests/unit/test_agent_compliance.py` pass.

---

## B6: Biased/bursty read-replica routing

- **Problem**: `aitbc/database/replica.py` uses `hash(time.time())` for replica selection, which is biased and bursty.
- **Fix**: Use `hash(str(uuid.uuid4()))` or a proper round-robin algorithm for replica selection.
- **Verify**: Read requests are distributed evenly across replicas.

---

## B7: PoA block proposer nonce bug

- **Problem**: `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` records `nonce - 1` for confirmed transactions instead of the actual nonce.
- **Fix**: Change the nonce recording to use the actual transaction nonce.
- **Verify**: Confirmed transactions have the correct nonce in the database.

---

## B8: CLI workflow commands

- **Problem**: `cli/aitbc_cli/commands/workflow.py` uses non-existent API paths for workflow operations.
- **Fix**: Update API paths to match the actual coordinator-api endpoints.
- **Verify**: `aitbc workflow list` and `aitbc workflow status` commands work correctly.

---

## B9: Consolidate duplicate logging modules

- **Problem**: `aitbc/log_utils/logging.py` duplicates functionality from `aitbc/aitbc_logging.py`.
- **Fix**: Make `log_utils/logging.py` a thin re-export shim that imports from `aitbc_logging.py`.
- **Verify**: All imports from `log_utils.logging` work correctly.

---

## B10: REPO_DIR environment-sourced

- **Problem**: `REPO_DIR` in `aitbc/constants.py` is hardcoded to `/opt/aitbc`.
- **Fix**: Make `REPO_DIR` environment-sourced via `AITBC_REPO_DIR` env var, with fallback to `/opt/aitbc`.
- **Verify**: `REPO_DIR` respects the `AITBC_REPO_DIR` environment variable.

---

## B11: Session rollback in PoA

- **Problem**: `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` lacks `session.rollback()` in the tx processing exception handler.
- **Fix**: Add `session.rollback()` in the exception handler to ensure transaction rollback on errors.
- **Verify**: Failed transactions are properly rolled back.

---

## Related Topics

- [Overview](./overview.md) - Release overview and task split overview
- [Agent A Tasks](./agent-a.md) - Type safety & shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.11 — Type Safety Hardening
**Agent**: Agent B (Bug Fixes, Infrastructure & Apps)
