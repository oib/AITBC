# v0.5.11 Type Safety Hardening — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Type Safety & Shared Core)

**Scope**: All MyPy type fixes in the `aitbc/` shared core library, `TypeAlias` migration, and stale `type: ignore` cleanup.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Fix MyPy errors in `aitbc/queues/` — implicit Optional, call-overload, unreachable | High | `queues/decorators.py`, `queues/worker.py`, `queues/task.py`, `queues/scheduler.py` | ✅ DONE |
| A2 | Fix `AITBCHTTPClient` response typing in `blockchain_service.py` — `.json()` on dict | High | `blockchain/blockchain_service.py` | ✅ DONE |
| A3 | Fix MyPy errors in `aitbc/database/` — `connection.py` and `replica.py` | High | `database/connection.py`, `database/replica.py` | ✅ DONE |
| A4 | Fix MyPy errors in `distributed_tracing.py` — import stubs, `TracerProvider` | High | `distributed_tracing.py` | ✅ DONE |
| A5 | Fix MyPy errors in `agent_bridge/src/integration_layer.py` — `union-attr`, `no-any-return` | High | `agent_bridge/src/integration_layer.py` | ✅ DONE |
| A6 | Fix MyPy errors in `api_utils.py` — implicit Optional | High | `api_utils.py` | ✅ DONE |
| A7 | Fix MyPy errors in `tracing.py` — import stubs, `attr-defined` | High | `tracing.py` | ✅ DONE |
| A8 | Fix MyPy errors in `agent_trading` + `agent_compliance` — `unused-ignore`, `no-any-return` | High | `agent_trading/src/trading_agent.py`, `agent_compliance/src/compliance_agent.py` | ✅ DONE |
| A9 | Fix MyPy errors in `ethereum_rpc.py`, `access_control.py`, `price_oracle.py` | High | `ethereum_rpc.py`, `access_control.py`, `oracles/price_oracle.py` | ✅ DONE |
| A10 | Fix MyPy errors in `agent_registry/src/discovery.py` — implicit Optional | High | `agent_registry/src/discovery.py` | ✅ DONE |
| A11 | Fix MyPy errors in `config/__init__.py` + `hierarchical_config.py` | High | `config/__init__.py`, `config/hierarchical_config.py` | ✅ DONE |
| A12 | Fix MyPy errors in `agent_registry/tests/` — `import-not-found` | High | `agent_registry/tests/test_unit_agent_registry.py`, `agent_registry/tests/test_integration_agent_registry.py`, `agent_registry/tests/test_edge_cases_agent_registry.py` | ✅ DONE |
| A13 | Fix MyPy errors in `agent_protocols/`, `events/`, `circuit_breaker/`, `stage_runner/`, `registration.py` | High | `agent_protocols/src/task_manager.py`, `agent_protocols/src/message_protocol.py`, `events/events.py`, `network/circuit_breaker.py`, `training_setup/stage_runner.py`, `agent_registry/src/registration.py` | ✅ DONE |
| A14 | Migrate deprecated `TypeAlias` syntax in `config/__init__.py` (UP040) | Medium | `config/__init__.py` | ✅ DONE |
| A15 | Clean up stale `type: ignore` comments flagged by `--warn-unused-ignores` | Medium | `agent_registry/tests/*.py` | ✅ DONE |

---

## A1: Queue system type fixes

- Type `last_called: list[float]` and `timer: list[asyncio.Task[Any] | None]` in `decorators.py`
- Remove unreachable `assert` in `decorators.py`
- Fix implicit Optional: `kwargs: dict[str, Any] | None = None` in `worker.py`, `task.py`, `scheduler.py`

---

## A2: Blockchain service response typing

- `AITBCHTTPClient.get()` and `.post()` return `dict[str, Any]` (already parsed JSON). Remove all redundant `.json()` calls.
- Cast `tx_hash` to `str` to fix `no-any-return`.

---

## A3: Database connection type fixes

- Type `self._connection: sqlite3.Connection | None` in `connection.py`. Use local variable with `assert` in `connect()`. Remove unused `type: ignore`.
- Type `self.primary_engine: Any`, annotate `self.replica_engines: list[Any]`, add return types to `get_read_engine`, `get_write_engine`, `get_session`, `_setup_monitoring` in `replica.py`.

---

## A4: Distributed tracing import fixes

- Add `type: ignore[import-not-found]` for Jaeger and HTTPX OpenTelemetry instrumentor imports.
- Type `_tracer` and `_provider` as `Any`. Add return types to `get_tracer`, `start_span`, `end_span`.
- Remove redundant `type: ignore[union-attr]`.

---

## A5: Agent bridge integration layer

- Type `self.session: aiohttp.ClientSession | None`.
- Add `assert self.session is not None` guards before all `self.session.get()`/`.post()` calls.
- Wrap `response.json()` with `dict()` to satisfy `no-any-return`.

---

## A6: API utilities

- Fix implicit Optional defaults in `build_cors_headers` (`allowed_origins`, `allowed_methods`, `allowed_headers`) and `sanitize_response` (`sensitive_fields`).

---

## A7: Tracing module

- Add `type: ignore[import-not-found]` for HTTPX instrumentor import.
- Change `_tracer` and `_tracer_provider` from `object | None` to `Any`.
- Change `get_tracer()` return type to `Any`.

---

## A8: Agent trading and compliance

- Fix `type: ignore` code from `import-not-found` to `import-untyped`.
- Cast `bool()` on `stop()` return and `dict()` on `get_status()` return.

---

## A9: Ethereum RPC, access control, price oracle

- `ethereum_rpc.py`: Type `self._w3: Any = None`, add `-> Any` return type to `_get_web3()`.
- `access_control.py`: Add `type: ignore[arg-type]` for `jwt.encode()` and `jwt.decode()`.
- `price_oracle.py`: Cast `json.load()` result to `dict[str, Any]`, add `cast` import.

---

## A10: Agent registry discovery

- Fix implicit Optional in `find_agents_by_capability` and `find_agents_by_type` (`filters: dict[str, Any] | None = None`).
- Update `_matches_filters` signature. Add `Any` import.

---

## A11: Config module

- Migrate deprecated `TypeAlias` syntax to `type` annotations (UP040). Remove `TypeAlias` from imports.
- Clean up unused `type: ignore` codes. Add `type: ignore[import-untyped]` for `yaml` import in `hierarchical_config.py`.

---

## A12: Agent registry tests

- Add `type: ignore[import-not-found]` on the **first** `import app` / `from app import ...` in each test file.
- Remove `type: ignore` from all subsequent `import app` statements in the same file.

---

## A13: Additional type fixes

- `task_manager.py`: Type `Task.completed_at: datetime | None`, `Task.result: dict[str, Any] | None`, `Task.error: str | None`.
- `message_protocol.py`: Type `self.messages: list[dict[str, Any]]` and `self.received_messages: list[dict[str, Any]]`.
- `events.py`: Fix `Event.timestamp: datetime | None = None`.
- `circuit_breaker.py`: Type `self.open_time: datetime | None = None`.
- `stage_runner.py`: Add `dict[str, Any]` annotation for `results` dict.
- `registration.py`: Fix implicit Optional for `metadata: dict[str, Any] | None = None`.

---

## A14: TypeAlias migration

- Part of A11 — migrate `TypeAlias` to `type` statement syntax in `config/__init__.py`.

---

## A15: Stale type: ignore cleanup

- Change `type: ignore[import]` to `type: ignore[import-not-found]` on first import in each test file.
- Remove `type: ignore` from subsequent `import app` in same file.
- Verify `type: ignore` in `aitbc_logging.py`, `log_utils/logging.py`, `caching/blockchain_cache.py`, `network/web3_utils.py` are still needed.

---

## A16: Debounce CancelledError bug

- In `queues/decorators.py`, wrap `await task` in `try/except asyncio.CancelledError` that returns `None` for superseded calls.
- Verify: superseded caller returns `None`, latest caller returns its value.

---

## Related Topics

- [Overview](./overview.md) - Release overview and task split overview
- [Agent B Tasks](./agent-b.md) - Bug fixes, infrastructure & apps implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.11 — Type Safety Hardening
**Agent**: Agent A (Type Safety & Shared Core)
