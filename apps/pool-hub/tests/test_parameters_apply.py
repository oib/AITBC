"""Pin for #1421: /v1/parameters/apply must update every miner's ServiceConfig.

Pre-fix the endpoint selected ServiceConfig by service_type alone and called
scalar_one_or_none(): with two miners offering the same service it raised
MultipleResultsFound (500), and with exactly one row it silently updated only
that miner while reporting applied=True. Governance parameter changes are
service-wide (the request carries no miner_id), so the fix applies the change
to all rows for the service_type and validates old_value per row.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from poolhub.app.routers.parameters import ParameterChangeRequest, apply_parameter_change


class _Scalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _Scalars:
        return _Scalars(self._rows)


class _Session:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.commit = AsyncMock()

    async def execute(self, stmt: Any) -> _Result:
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
