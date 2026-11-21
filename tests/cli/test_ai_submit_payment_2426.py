"""#2426: ``ai submit --wait`` must survive slow escrow seals.

Live failure (node0, 21 Nov): ``POST /v1/payments`` legitimately runs for
minutes while the coordinator seals the ESCROW_LOCK — the shared 30s
client timed out, each timeout counted against the circuit breaker, and
after 5 the breaker opened and killed the ``--wait`` poll path even though
the server had accepted the job. Fixes:

- ``ai submit`` builds its coordinator client with
  ``enable_circuit_breaker=False`` (same precedent as the market
  escrow/host payment clients).
- ``_create_escrow_payment`` posts through ``_escrow_payment_client`` — a
  dedicated client with a seal-horizon timeout (240s) and the breaker
  off — and reconciles an ambiguous submit against
  ``GET /v1/jobs/{id}/payment`` before declaring failure (#2340 pattern).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import aitbc_cli.commands.ai as _ai
from aitbc_cli.utils.http_client import NetworkError

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
NODE_WALLET = "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01"

_LOCK = ({"from": BUYER, "payload": {"provider": PROVIDER}, "nonce": 3, "fee": 36}, "0xsig")


def _call_create(client, **over):
    kwargs = {
        "ctx": None,
        "coord_http_client": client,
        "rpc_url": "http://127.0.0.1:8202",
        "job_id": "coord-job-1",
        "amount": "0.1",
        "token": "AITBC",
        "buyer_address": BUYER,
        "provider_address": PROVIDER,
        "private_key": "0x" + "01" * 32,
        "node_wallet": NODE_WALLET,
        "chain_id": "bc-2",
        "offer_id": None,
        "offer_quantity": None,
    }
    kwargs.update(over)
    with patch("aitbc_cli.commands.ai.create_signed_escrow_lock", return_value=_LOCK):
        return _ai._create_escrow_payment(**kwargs)


class _FakeCoordClient:
    """Test double — not an AITBCHTTPClient, so it is used as-is."""

    def __init__(self, post_side_effect=None, get_side_effect=None):
        self.posts: list[dict] = []
        self.gets: list[str] = []
        self._post_side_effect = post_side_effect
        self._get_side_effect = get_side_effect

    def post(self, path, json=None, **kwargs):
        self.posts.append({"path": path, "json": json})
        if self._post_side_effect:
            raise self._post_side_effect
        return {"payment_id": "pay-1", "status": "escrowed"}

    def get(self, path, **kwargs):
        self.gets.append(path)
        if self._get_side_effect:
            return self._get_side_effect(path)
        raise AssertionError("unexpected GET")


class TestEscrowPaymentClient:
    def test_real_client_gets_seal_timeout_and_no_breaker(self):
        """The payments POST must not share the 30s/breaker client."""
        captured: dict = {}

        class _FakeReal:
            def __init__(self, **kw):
                captured.update(kw)

        coord = _FakeReal.__new__(_FakeReal)
        coord.base_url = "http://coord:8203"
        coord.headers = {"X-API-Key": "k"}

        # Patch the class the helper isinstance-checks and constructs, so
        # the "real client" branch runs without network.
        with patch.object(_ai, "AITBCHTTPClient", _FakeReal):
            out = _ai._escrow_payment_client(coord)  # type: ignore[arg-type]
        assert isinstance(out, _FakeReal)
        assert captured["timeout"] == _ai._AI_PAYMENT_POST_TIMEOUT == 240
        assert captured["enable_circuit_breaker"] is False
        assert captured["base_url"] == "http://coord:8203"
        assert captured["headers"] == {"X-API-Key": "k"}

    def test_test_double_returned_unchanged(self):
        fake = _FakeCoordClient()
        assert _ai._escrow_payment_client(fake) is fake  # type: ignore[arg-type]


class TestCreateEscrowPaymentReconcile:
    def test_ambiguous_post_reconciles_via_payment_get(self, monkeypatch):
        """POST times out but the row committed server-side -> return it."""
        monkeypatch.setattr(_ai, "_AI_PAYMENT_RECONCILE_DELAY", 0)
        view = {"payment_id": "pay-9", "status": "escrowed"}
        client = _FakeCoordClient(
            post_side_effect=NetworkError("POST request failed: Read timed out"),
            get_side_effect=lambda path: view if path == "/v1/jobs/coord-job-1/payment" else None,
        )
        warnings: list[str] = []
        with patch.object(_ai, "warning", lambda m, **kw: warnings.append(m)):
            result = _call_create(client)
        assert result == view
        assert client.gets == ["/v1/jobs/coord-job-1/payment"]
        assert warnings and "reconciled" in warnings[0]

    def test_ambiguous_post_without_row_reraises(self, monkeypatch):
        """No payment row after the reconcile window -> the NetworkError
        propagates to the caller's honest abort path."""
        monkeypatch.setattr(_ai, "_AI_PAYMENT_RECONCILE_ATTEMPTS", 2)
        monkeypatch.setattr(_ai, "_AI_PAYMENT_RECONCILE_DELAY", 0)
        client = _FakeCoordClient(
            post_side_effect=NetworkError("POST request failed: Read timed out"),
            get_side_effect=lambda path: None,
        )
        with pytest.raises(NetworkError):
            _call_create(client)
        assert client.gets == ["/v1/jobs/coord-job-1/payment"] * 2

    def test_successful_post_never_reconciles(self):
        client = _FakeCoordClient()
        result = _call_create(client)
        assert result == {"payment_id": "pay-1", "status": "escrowed"}
        assert client.gets == []


class TestSubmitClientBreaker:
    def test_submit_client_disables_circuit_breaker(self):
        """``ai submit`` must build its coordinator client with the breaker
        off — the --wait path cannot be killed by accrued slow-call
        failures (#2426)."""
        import inspect

        import sys

        # ``ai.submit`` is shadowed by the re-exported click Command; the
        # module itself lives in sys.modules.
        submit_mod = sys.modules["aitbc_cli.commands.ai.submit"]

        src = inspect.getsource(submit_mod.submit.callback)
        assert "enable_circuit_breaker=False" in src
