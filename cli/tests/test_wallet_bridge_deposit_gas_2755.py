"""#2755: ``wallet bridge deposit`` estimates gas for the ETH deposit tx.

``_send_eth_deposit_tx`` broadcasts over raw JSON-RPC (httpx), and the
deposit carries ``data`` so it is a contract call. It now issues
``eth_estimateGas`` alongside nonce/gasPrice and uses estimate + 25%
headroom instead of the old fixed 100000; an estimate failure aborts
before ``eth_sendRawTransaction``.
"""

from __future__ import annotations

import math
from decimal import Decimal
from types import SimpleNamespace

import click
import httpx
import pytest
from eth_account import Account as EthAccount

from aitbc_cli.commands.wallet.bridge import _send_eth_deposit_tx

PRIVKEY = "0x" + "11" * 32
BRIDGE = "0x" + "55" * 20
HEX_DATA = "0x1234abcd"
ESTIMATE = 200_000
EXPECTED_GAS = math.ceil(ESTIMATE * 5 / 4)


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient; records every JSON-RPC body posted."""

    def __init__(self, posts, estimate_payload):
        self._posts = posts
        self._estimate_payload = estimate_payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, **kwargs):
        self._posts.append(json)
        method = json["method"]
        if method == "eth_getTransactionCount":
            return _Resp({"result": hex(5)})
        if method == "eth_gasPrice":
            return _Resp({"result": hex(1_000_000_000)})
        if method == "eth_estimateGas":
            return _Resp(self._estimate_payload)
        if method == "eth_sendRawTransaction":
            return _Resp({"result": "0xtxhash"})
        raise AssertionError(f"unexpected method {method}")


@pytest.fixture
def harness(monkeypatch):
    account = EthAccount.from_key(PRIVKEY)
    derived = account.address
    posts: list[dict] = []
    estimate_payload = {"result": hex(ESTIMATE)}
    client = _FakeClient(posts, estimate_payload)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)

    captured = {}

    def fake_sign(self, tx, blobs=None):
        captured["tx"] = tx
        return SimpleNamespace(raw_transaction=b"\x00\x01")

    # from_key returns a LocalAccount, not the Account facade class.
    monkeypatch.setattr(type(account), "sign_transaction", fake_sign)
    monkeypatch.delenv("ETH_NETWORK", raising=False)
    return SimpleNamespace(derived=derived, posts=posts, captured=captured, client=client)


def _send(harness):
    return _send_eth_deposit_tx(
        ait_address=harness.derived,
        eth_private_key=PRIVKEY,
        bridge_eth_address=BRIDGE,
        eth_amount=Decimal("0.5"),
        hex_data=HEX_DATA,
        rpc_url="http://rpc.test",
    )


def test_deposit_tx_uses_estimated_gas(harness):
    tx_hash = _send(harness)
    assert tx_hash == "0xtxhash"
    methods = [p["method"] for p in harness.posts]
    assert "eth_estimateGas" in methods
    assert methods.index("eth_estimateGas") < methods.index("eth_sendRawTransaction")

    est_call = next(p for p in harness.posts if p["method"] == "eth_estimateGas")
    est_tx = est_call["params"][0]
    assert est_tx["from"] == harness.derived
    assert est_tx["to"] == BRIDGE
    assert est_tx["data"] == HEX_DATA
    assert est_tx["value"] == hex(int(Decimal("0.5") * Decimal(10**18)))

    tx = harness.captured["tx"]
    assert tx["gas"] == EXPECTED_GAS
    assert tx["gas"] != 100_000  # not the old hardcoded limit
    assert tx["data"] == HEX_DATA
    assert tx["value"] == int(Decimal("0.5") * Decimal(10**18))


def test_estimate_error_aborts_before_send(harness, capsys):
    harness.client._estimate_payload = {"error": {"code": -32000, "message": "execution reverted"}}
    with pytest.raises(click.Abort):
        _send(harness)
    methods = [p["method"] for p in harness.posts]
    assert "eth_sendRawTransaction" not in methods
    captured = capsys.readouterr()
    assert "eth_estimateGas failed" in captured.out + captured.err


def test_estimate_missing_result_aborts_before_send(harness):
    harness.client._estimate_payload = {"jsonrpc": "2.0", "id": 2}
    with pytest.raises(click.Abort):
        _send(harness)
    methods = [p["method"] for p in harness.posts]
    assert "eth_sendRawTransaction" not in methods


def test_estimate_http_error_aborts_before_send(harness, monkeypatch):
    class _BadResp(_Resp):
        pass

    original_post = _FakeClient.post

    async def post_with_bad_estimate(self, url, json=None, **kwargs):
        if json["method"] == "eth_estimateGas":
            self._posts.append(json)
            return _Resp({}, status_code=500)
        return await original_post(self, url, json=json, **kwargs)

    monkeypatch.setattr(_FakeClient, "post", post_with_bad_estimate)
    with pytest.raises(click.Abort):
        _send(harness)
    methods = [p["method"] for p in harness.posts]
    assert "eth_sendRawTransaction" not in methods
