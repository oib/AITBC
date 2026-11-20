"""#2303: `gpu refund` reaches coordinator-created rentals through the coordinator."""

import pytest

import aitbc_cli.commands.market.gpu as gpu_mod
from aitbc.exceptions import NetworkError


class _Resp:
    def __init__(self, code):
        self.status_code = code

    def json(self):
        return {"detail": f"http {self.status_code}"}


class _HttpNetworkError(NetworkError):
    def __init__(self, code):
        super().__init__(str(code))
        self.response = _Resp(code)


def _net_error(code):
    return _HttpNetworkError(code)


class _Client:
    def __init__(self, get=None, post=None):
        self._get, self._post, self.calls = get, post, []

    def get(self, path, **kw):
        self.calls.append(("GET", path))
        if isinstance(self._get, Exception):
            raise self._get
        return self._get

    def post(self, path, **kw):
        self.calls.append(("POST", path, kw.get("json")))
        if isinstance(self._post, Exception):
            raise self._post
        return self._post


def _patch(monkeypatch, client):
    monkeypatch.setattr(gpu_mod, "AITBCHTTPClient", lambda *a, **k: client)
    monkeypatch.setattr(gpu_mod, "_coordinator_url", lambda: "http://c")
    monkeypatch.setattr(gpu_mod, "_auth_headers", lambda ctx: {})


def test_refunds_through_coordinator_payment(monkeypatch):
    c = _Client(get={"payment_id": "pay1"}, post={"status": "refunded", "payment_id": "pay1"})
    _patch(monkeypatch, c)
    out = gpu_mod._refund_via_coordinator(None, "job1", "why")
    assert out == {"status": "refunded", "payment_id": "pay1"}
    assert c.calls[0] == ("GET", "/v1/jobs/job1/payment")
    assert c.calls[1] == ("POST", "/v1/payments/pay1/refund", {"job_id": "job1", "payment_id": "pay1", "reason": "why"})


def test_no_coordinator_payment_returns_none_for_market_fallback(monkeypatch):
    _patch(monkeypatch, _Client(get=_net_error(404)))
    assert gpu_mod._refund_via_coordinator(None, "job1", "") is None


@pytest.mark.parametrize("code", [401, 403, 500])
def test_other_lookup_failures_exit_nonzero(monkeypatch, code):
    _patch(monkeypatch, _Client(get=_net_error(code)))
    with pytest.raises(SystemExit):
        gpu_mod._refund_via_coordinator(None, "job1", "")


def test_refund_post_failure_exits_nonzero(monkeypatch):
    _patch(monkeypatch, _Client(get={"payment_id": "p"}, post=_net_error(403)))
    with pytest.raises(SystemExit):
        gpu_mod._refund_via_coordinator(None, "job1", "")


def test_refund_command_tries_the_coordinator_before_the_market_service():
    import inspect

    src = inspect.getsource(gpu_mod.refund.callback or gpu_mod._refund_via_coordinator)
    assert src.index("_refund_via_coordinator(") < src.index("market_service_url")
