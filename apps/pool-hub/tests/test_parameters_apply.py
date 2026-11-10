"""Pin for #1421: /v1/parameters/apply must update every miner's ServiceConfig.

Pre-fix the endpoint selected ServiceConfig by service_type alone and called
scalar_one_or_none(): with two miners offering the same service it raised
MultipleResultsFound (500), and with exactly one row it silently updated only
that miner while reporting applied=True. Governance parameter changes are
service-wide (the request carries no miner_id), so the fix applies the change
to all rows for the service_type and validates old_value per row.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from poolhub.app.deps import get_db_session
from poolhub.app.routers import parameters as parameters_module
from poolhub.app.routers.parameters import (
    ParameterChangeRequest,
    _governance_auth,
    apply_parameter_change,
)


class _Scalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        # UPDATE ... WHERE guard (#1600) inspects rowcount; the mock reports
        # every fixture row as matched, which is what a non-raced apply sees.
        self.rowcount = len(rows)

    def scalars(self) -> _Scalars:
        return _Scalars(self._rows)


class _Session:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.statements: list[Any] = []
        self.commit = AsyncMock()

    async def execute(self, stmt: Any) -> _Result:
        self.statements.append(stmt)
        return _Result(self._rows)


def _config(**overrides: Any) -> MagicMock:
    cfg = MagicMock()
    cfg.max_concurrent = overrides.get("max_concurrent", 1)
    cfg.enabled = overrides.get("enabled", True)
    cfg.pricing = overrides.get("pricing", {})
    cfg.config = overrides.get("config", {})
    cfg.capabilities = overrides.get("capabilities", [])
    cfg.updated_at = None
    return cfg


def _change(**overrides: Any) -> ParameterChangeRequest:
    base: dict[str, Any] = {
        "proposal_id": "prop-1",
        "target_service": "whisper",
        "parameter_name": "max_concurrent",
        "new_value": 4,
    }
    base.update(overrides)
    return ParameterChangeRequest(**base)


@pytest.mark.asyncio
async def test_apply_updates_all_miners_for_service_type() -> None:
    a, b = _config(max_concurrent=1), _config(max_concurrent=2)
    session = _Session([a, b])

    resp = await apply_parameter_change(_change(), session, MagicMock())  # type: ignore[arg-type]

    assert resp.applied is True
    assert a.max_concurrent == 4
    assert b.max_concurrent == 4
    assert a.updated_at is not None and b.updated_at is not None
    assert session.commit.await_count == 1
    # Multi-row response reports per-row old values
    assert resp.old_value == [1, 2]
    assert "2 miner config(s)" in resp.message


@pytest.mark.asyncio
async def test_apply_single_row_returns_scalar_old_value() -> None:
    cfg = _config(max_concurrent=3)
    session = _Session([cfg])

    resp = await apply_parameter_change(_change(new_value=7), session, MagicMock())  # type: ignore[arg-type]

    assert cfg.max_concurrent == 7
    assert resp.old_value == 3
    assert "1 miner config(s)" in resp.message


@pytest.mark.asyncio
async def test_apply_no_rows_is_404() -> None:
    session = _Session([])
    with pytest.raises(HTTPException) as exc:
        await apply_parameter_change(_change(), session, MagicMock())  # type: ignore[arg-type]
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_apply_old_value_mismatch_on_any_row_is_409() -> None:
    a, b = _config(max_concurrent=1), _config(max_concurrent=9)
    session = _Session([a, b])

    with pytest.raises(HTTPException) as exc:
        await apply_parameter_change(_change(old_value=1), session, MagicMock())  # type: ignore[arg-type]
    assert exc.value.status_code == 409
    # Nothing committed, nothing mutated
    assert session.commit.await_count == 0
    assert a.max_concurrent == 1


@pytest.mark.asyncio
async def test_apply_old_value_match_updates_all() -> None:
    a, b = _config(enabled=True), _config(enabled=True)
    session = _Session([a, b])

    resp = await apply_parameter_change(
        _change(parameter_name="enabled", new_value=False, old_value=True),
        session,
        MagicMock(),  # type: ignore[arg-type]
    )

    assert resp.applied is True
    assert a.enabled is False and b.enabled is False


# --- Governance auth gate -------------------------------------------------
#
# The five pins above call apply_parameter_change() directly, which bypasses
# the FastAPI dependency layer entirely — a mutant that dropped the
# _governance_auth Depends (or flipped auth_enabled) would survive them all.
# These pins exercise the authenticator itself and the mounted route.


def _conn(headers: dict[str, str]) -> Any:
    """Minimal HTTPConnection stand-in for APIKeyAuthenticator.__call__."""
    return SimpleNamespace(headers=headers)


@pytest.mark.asyncio
async def test_governance_auth_rejects_missing_key() -> None:
    with pytest.raises(HTTPException) as exc:
        await _governance_auth(_conn({}))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_governance_auth_rejects_wrong_key() -> None:
    with pytest.raises(HTTPException) as exc:
        await _governance_auth(_conn({"X-PoolHub-Key": "not-the-secret"}))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_governance_auth_accepts_configured_key() -> None:
    resp = await _governance_auth(_conn({"X-PoolHub-Key": _governance_auth.expected_key or ""}))
    assert resp["role"] == "governance"
    assert resp["auth_type"] == "api_key"


def _parameters_client(session: _Session) -> TestClient:
    """Mount just the parameters router so the auth dependency is exercised."""
    app = FastAPI()
    app.include_router(parameters_module.router, prefix="/v1")

    async def _db() -> Any:
        yield session

    app.dependency_overrides[get_db_session] = _db
    return TestClient(app)


def test_route_rejects_parameter_mutation_without_key() -> None:
    session = _Session([_config()])
    client = _parameters_client(session)
    resp = client.post(
        "/v1/parameters/apply",
        json={
            "proposal_id": "prop-1",
            "target_service": "whisper",
            "parameter_name": "max_concurrent",
            "new_value": 4,
        },
    )
    assert resp.status_code == 401
    assert session.commit.await_count == 0


def test_route_rejects_parameter_mutation_with_wrong_key() -> None:
    session = _Session([_config()])
    client = _parameters_client(session)
    resp = client.post(
        "/v1/parameters/apply",
        headers={"X-PoolHub-Key": "attacker-key"},
        json={
            "proposal_id": "prop-1",
            "target_service": "whisper",
            "parameter_name": "max_concurrent",
            "new_value": 4,
        },
    )
    assert resp.status_code == 401
    assert session.commit.await_count == 0


def test_route_applies_parameter_mutation_with_governance_key() -> None:
    cfg = _config(max_concurrent=1)
    session = _Session([cfg])
    client = _parameters_client(session)
    resp = client.post(
        "/v1/parameters/apply",
        headers={"X-PoolHub-Key": _governance_auth.expected_key or ""},
        json={
            "proposal_id": "prop-1",
            "target_service": "whisper",
            "parameter_name": "max_concurrent",
            "new_value": 4,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["applied"] is True
    assert cfg.max_concurrent == 4


# --- Parameter-name and value-type validation ------------------------------


@pytest.mark.asyncio
async def test_apply_rejects_non_governance_parameter() -> None:
    cfg = _config()
    session = _Session([cfg])
    with pytest.raises(HTTPException) as exc:
        await apply_parameter_change(
            _change(parameter_name="secret_key", new_value="x"),
            session,
            MagicMock(),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 400
    assert session.commit.await_count == 0
    assert session.statements == []  # rejected before any DB read


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("max_concurrent", "4"),  # str, not int
        ("max_concurrent", 4.5),  # float, not int
        ("max_concurrent", True),  # bool is an int subclass — still wrong type
        ("max_concurrent", -1),  # negative concurrency is meaningless
        ("enabled", "yes"),
        ("enabled", 1),  # int is not bool
        ("pricing", "cheap"),
        ("pricing", [("a", 1)]),
        ("config", "{}"),
        ("capabilities", {"a": 1}),
        ("capabilities", "llm"),
    ],
)
async def test_apply_rejects_wrong_value_type(param: str, value: Any) -> None:
    session = _Session([_config()])
    with pytest.raises(HTTPException) as exc:
        await apply_parameter_change(
            _change(parameter_name=param, new_value=value),
            session,
            MagicMock(),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 400
    assert session.commit.await_count == 0
    assert session.statements == []  # rejected before any DB read


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("max_concurrent", 0),
        ("max_concurrent", 8),
        ("enabled", True),
        ("pricing", {"per_hour": "0.5"}),
        ("config", {"nested": {"a": 1}}),
        ("capabilities", ["chat", "vision"]),
    ],
)
async def test_apply_accepts_valid_value_types(param: str, value: Any) -> None:
    cfg = _config()
    session = _Session([cfg])
    resp = await apply_parameter_change(
        _change(parameter_name=param, new_value=value),
        session,
        MagicMock(),  # type: ignore[arg-type]
    )
    assert resp.applied is True
    assert getattr(cfg, param) == value


@pytest.mark.asyncio
async def test_apply_statement_filters_by_target_service_type() -> None:
    """The SELECT must scope to service_type — a mutant dropping the WHERE
    clause would update every ServiceConfig row regardless of service."""
    session = _Session([_config()])
    await apply_parameter_change(
        _change(target_service="llm_inference"),
        session,
        MagicMock(),  # type: ignore[arg-type]
    )
    assert len(session.statements) == 1
    compiled = str(session.statements[0].compile())
    assert "service_type" in compiled
    assert "llm_inference" in str(session.statements[0].compile().params.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_value", [0, 11, 10**30, -1, True, 4.0, "4"])
async def test_apply_max_concurrent_out_of_service_bounds_is_400(bad_value: Any) -> None:
    """#1421 second pass: governance apply must honour the same 1..10 bound the
    service's own ServiceConfig schemas enforce — 0 would drain capacity and
    an out-of-range int overflows the Integer column on PostgreSQL."""
    cfg = _config(max_concurrent=1)
    session = _Session([cfg])
    with pytest.raises(HTTPException) as exc:
        await apply_parameter_change(_change(new_value=bad_value), session, MagicMock())  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert session.commit.await_count == 0
    assert cfg.max_concurrent == 1


@pytest.mark.asyncio
async def test_apply_capabilities_rejects_non_string_items() -> None:
    """capabilities is list[str] on the service schema; [1, 2] is a list but
    violates the column contract."""
    cfg = _config(capabilities=["gpu"])
    session = _Session([cfg])
    with pytest.raises(HTTPException) as exc:
        await apply_parameter_change(
            _change(parameter_name="capabilities", new_value=[1, 2]),
            session,
            MagicMock(),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 400
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_apply_capabilities_accepts_string_list() -> None:
    cfg = _config(capabilities=[])
    session = _Session([cfg])
    resp = await apply_parameter_change(
        _change(parameter_name="capabilities", new_value=["gpu", "cuda"]),
        session,
        MagicMock(),  # type: ignore[arg-type]
    )
    assert resp.applied is True
    assert cfg.capabilities == ["gpu", "cuda"]
