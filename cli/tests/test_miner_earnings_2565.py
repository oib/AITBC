"""AUDIT-MINER-EARNINGS-ROUTE-1 (#2565): ``miner earnings`` called GET on
the POST-only ``/v1/miners/{id}/jobs`` route, got a 405, and reported
``total_earnings: 0.0`` alongside the failure string — fake zero totals.

Now it POSTs ``/v1/miners/{id}/earnings`` (the real route) and failure
payloads carry no earnings fields at all.
"""

import miner_management as mm
import pytest
import requests


class _Resp:
    def __init__(self, status_code=200, payload=None, json_exc=None):
        self.status_code = status_code
        self._payload = payload or {}
        self._json_exc = json_exc

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._payload


@pytest.fixture
def posted(monkeypatch):
    from types import SimpleNamespace

    state = SimpleNamespace(calls=[], result=_Resp())

    def _post(url, headers=None, params=None, timeout=None, **kw):
        state.calls.append({"url": url, "headers": headers, "params": params})
        return state.result

    monkeypatch.setattr(mm.requests, "post", _post)
    return state


def test_earnings_posts_to_earnings_route(posted):
    posted.result = _Resp(
        payload={
            "total_earnings": "12.5",
            "pending_earnings": "2.5",
            "paid_earnings": "10.0",
            "completed_jobs": 5,
            "currency": "AITBC",
        }
    )
    out = mm.check_earnings("m1", api_key="k", coordinator_url="http://c", period="all")
    assert out is not None
    assert out["status"].startswith("📊")
    assert out["total_earnings"] == "12.5"
    assert out["paid_earnings"] == "10.0"
    assert out["pending_earnings"] == "2.5"
    assert out["jobs_completed"] == 5
    assert out["average_payment"] == "2.5"
    assert out["currency"] == "AITBC"
    assert posted.calls[0]["url"] == "http://c/v1/miners/m1/earnings"
    assert posted.calls[0]["headers"] == {"X-API-Key": "k"}
    assert posted.calls[0]["params"] == {}


def test_earnings_period_maps_to_from_time(posted):
    posted.result = _Resp(payload={"total_earnings": "0", "completed_jobs": 0})
    mm.check_earnings("m1", coordinator_url="http://c", period="week")
    assert "from_time" in posted.calls[0]["params"]


@pytest.mark.parametrize("period", ["day", "week", "month", "24h", "7d", "30d", "all", "bogus"])
def test_earnings_periods_accepted(posted, period):
    posted.result = _Resp(payload={"total_earnings": "0", "completed_jobs": 0})
    out = mm.check_earnings("m1", coordinator_url="http://c", period=period)
    assert out is not None
    assert out["period"] == period


def test_earnings_http_error_has_no_zero_totals(posted):
    posted.result = _Resp(status_code=405)
    out = mm.check_earnings("m1", coordinator_url="http://c")
    assert out is not None
    assert out["status"].startswith("❌")
    assert "405" in out["status"]
    for fabricated in ("total_earnings", "jobs_completed", "average_payment"):
        assert fabricated not in out


def test_earnings_connection_error_has_no_zero_totals(monkeypatch):
    def _raise(*a, **kw):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(mm.requests, "post", _raise)
    out = mm.check_earnings("m1", coordinator_url="http://c")
    assert out is not None
    assert out["status"].startswith("❌")
    assert "total_earnings" not in out


def test_earnings_bad_json_reported(posted):
    posted.result = _Resp(json_exc=ValueError("no json"))
    out = mm.check_earnings("m1", coordinator_url="http://c")
    assert out is not None
    assert out["status"].startswith("❌")
    assert "total_earnings" not in out
