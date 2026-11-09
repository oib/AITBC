"""#1407: check_service_health must not report non-2xx as healthy.

The old code returned ``"status": "healthy"`` for any HTTP response —
including 500s — with a hardcoded ``response_time`` of 0.1 and the
"ai" entry pointed at the exchange port (8106 instead of 8005).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import monitoring_service.main as mon  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeClient:
    status_code = 200

    def __init__(self, *a: Any, **kw: Any) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url: str):
        return _FakeResponse(self.status_code, {"ok": True})


@pytest.fixture
def fake_client(monkeypatch):
    def _install(status_code: int):
        class C(_FakeClient):
            pass

        C.status_code = status_code
        monkeypatch.setattr(mon.httpx, "AsyncClient", C)

    return _install


@pytest.mark.asyncio
async def test_2xx_is_healthy(fake_client) -> None:
    fake_client(200)
    result = await mon.check_service_health("svc", {"url": "http://x"})
    assert result["status"] == "healthy"
    assert result["http_status"] == 200
    assert "response_time" not in result  # replaced by measured response_time_ms
    assert result["response_time_ms"] >= 0


@pytest.mark.asyncio
async def test_500_is_unhealthy(fake_client) -> None:
    fake_client(500)
    result = await mon.check_service_health("svc", {"url": "http://x"})
    assert result["status"] == "unhealthy"
    assert result["http_status"] == 500


def test_ai_entry_points_at_ai_engine_port() -> None:
    assert mon.SERVICES["ai"]["port"] == 8005
    assert mon.SERVICES["ai"]["url"] == "http://localhost:8005"
