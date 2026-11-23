"""#2545/#2546/#2547 pins for `market exchange mint-ait`.

The mint flow used to verify the deposit before checking the signing key,
treasury account or submit — stranding rows at 'verified' — pay the
operator's configured wallet instead of the deposit's recipient, mark the
deposit completed at mempool admission, and sign consecutive runs with the
same sealed nonce. These tests drive the real command with the wallet
daemon and chain RPC stubbed at the HTTP boundary.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from click.testing import CliRunner

from aitbc_cli.commands.market import exchange as ex

RECIPIENT = "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC"
OPERATOR_WALLET = "0xDDdDddDdDdddDDddDDddDDDDdDdDDdDDdDDDDDDd"
TREASURY = "0xaAaAaAaaAaAaAaaAaAAAAAAAAaaaAaAaAaaAaaAa"
DEPOSIT_ID = "dep-1"
SEALED_TX = "0x" + "11" * 32
PENDING_TX = "0x" + "22" * 32


def _deposit(status: str = "pending", **over) -> dict:
    d = {
        "id": DEPOSIT_ID,
        "status": status,
        "amount_eth": "0.1",
        "amount_ait": "100.0",
        "from_address": "0xethsender",
        "recipient": RECIPIENT,
        "ait_tx_hash": None,
    }
    d.update(over)
    return d


class _Config:
    api_key = "k"
    wallet_daemon_url = "http://wallet.test:8108"
    wallet_api_key = "wk"
    wallet_address = OPERATOR_WALLET
    chain_id = "bc-2"
    genesis_wallet_address = TREASURY
    genesis_wallet_private_key = SimpleNamespace(get_secret_value=lambda: "0x" + "b" * 64)
    blockchain_rpc_url = "http://chain.test"


class _Chain:
    """Scripted chain-RPC answers; records every request."""

    def __init__(self):
        self.gets: list[str] = []
        self.posts: list[dict] = []
        # /rpc/transaction/<hash> answers, keyed by hash
        self.tx_status: dict[str, dict] = {}
        self.sealed_txs: list[dict] = []
        self.pending_txs: list[dict] = []
        self.mempool_nonces: list[int] = []
        self.account_nonce = 5

    @staticmethod
    def _resp(data, status_code: int = 200) -> httpx.Response:
        return httpx.Response(status_code, json=data)

    def get(self, url: str, **_kw):
        self.gets.append(url)
        path = url.split("/rpc", 1)[1] if "/rpc" in url else url
        if path.startswith("/accounts/"):
            return self._resp({"nonce": self.account_nonce, "balance": 10**12})
        if path.startswith("/transactions"):
            return self._resp(self.sealed_txs)
        if path.startswith("/mempool"):
            txs = [{"from": TREASURY, "nonce": n, "payload": {}} for n in self.mempool_nonces]
            return self._resp({"success": True, "transactions": txs, "count": len(txs)})
        if path.startswith("/transaction/"):
            tx_hash = path.split("/")[-1].split("?")[0]
            return self._resp(self.tx_status.get(tx_hash, {"status": "pending"}))
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, **kwargs):
        self.posts.append({"url": url, "json": kwargs.get("json")})
        return self._resp({"transaction_hash": SEALED_TX})


class _WalletClient:
    """Stands in for AITBCHTTPClient on both base_urls.

    The wallet daemon (8108) serves /v1/exchange/*; the chain RPC client
    built for the mempool nonce probe hits /rpc/mempool on the chain URL.
    """

    deposit: dict
    calls: list[tuple[str, str]] = []
    mempool_nonces: list[int] = []
    complete_body: dict | None = None

    def __init__(self, base_url: str = "", timeout=30, api_key=None, **_):
        self.base_url = base_url

    def get(self, endpoint: str, params=None, headers=None):
        type(self).calls.append(("GET", endpoint))
        if endpoint.startswith("/rpc/"):
            # pending_nonce_floor's mempool probe — always readable-empty here
            return {"success": True, "transactions": [], "count": 0}
        assert endpoint == f"/v1/exchange/deposits/{DEPOSIT_ID}"
        return type(self).deposit

    def post(self, endpoint: str, json=None, params=None, headers=None, **_):
        type(self).calls.append(("POST", endpoint))
        if endpoint.endswith("/verify"):
            return {"success": True}
        if endpoint.endswith("/complete"):
            type(self).complete_body = json
            return {"success": True}
        raise AssertionError(f"unexpected POST {endpoint}")


@pytest.fixture
def harness(monkeypatch):
    chain = _Chain()
    chain.tx_status[SEALED_TX] = {"status": "confirmed", "block_height": 100}
    _WalletClient.deposit = _deposit()
    _WalletClient.calls = []
    _WalletClient.complete_body = None

    cfg = _Config()
    monkeypatch.setattr(ex, "get_config", lambda: cfg)
    monkeypatch.setattr(ex, "AITBCHTTPClient", _WalletClient)
    monkeypatch.setattr(ex, "_sign_transaction", lambda payload, key: "0xsig")
    monkeypatch.setattr("click.confirm", lambda *a, **k: True)
    monkeypatch.setattr(httpx, "get", chain.get)
    monkeypatch.setattr(httpx, "post", chain.post)
    return chain


def _run():
    return CliRunner().invoke(ex.mint_ait, ["--deposit-id", DEPOSIT_ID], obj={})


def _posts(chain):
    return [p for p in chain.posts if p["url"].endswith("/rpc/transaction")]


# --- #2547: pay the deposit recipient, never the operator wallet ---------


def test_transfer_pays_deposit_recipient_not_operator_wallet(harness):
    res = _run()
    assert res.exit_code == 0, res.output
    tx = _posts(harness)[0]["json"]
    assert tx["to"] == RECIPIENT
    assert tx["to"] != OPERATOR_WALLET


def test_missing_recipient_refuses_before_verify(harness):
    _WalletClient.deposit = _deposit(recipient=None)
    res = _run()
    assert res.exit_code != 0
    assert "no AIT recipient" in res.output
    assert not any(c[0] == "POST" and c[1].endswith("/verify") for c in _WalletClient.calls)
    assert not _posts(harness)


def test_invalid_recipient_refuses(harness):
    _WalletClient.deposit = _deposit(recipient="not-an-address")
    res = _run()
    assert res.exit_code != 0
    assert "not a valid AIT address" in res.output
    assert not _posts(harness)


# --- #2545: verify only after transfer preconditions; resumable ---------


def test_missing_signing_key_never_verifies(harness, monkeypatch):
    monkeypatch.setattr(_Config, "genesis_wallet_private_key", None)
    res = _run()
    assert res.exit_code != 0
    assert "No signing key" in res.output
    # The deposit must stay pending — the verify flip never ran.
    assert not any(c[0] == "POST" and c[1].endswith("/verify") for c in _WalletClient.calls)
    assert not _posts(harness)


def test_unknown_treasury_account_never_verifies(harness, monkeypatch):
    def _account_404(url, **kw):
        return httpx.Response(404, json={"detail": "not found"})

    # _treasury_sender_nonce uses httpx.get directly; 404 aborts preflight.
    orig_get = httpx.get

    def routed(url, **kw):
        if "/rpc/accounts/" in url:
            return httpx.Response(404, json={"detail": "not found"})
        return orig_get(url, **kw)

    monkeypatch.setattr(httpx, "get", routed)
    res = _run()
    assert res.exit_code != 0
    assert not any(c[0] == "POST" and c[1].endswith("/verify") for c in _WalletClient.calls)


def test_verified_deposit_resumes_without_reverify(harness):
    _WalletClient.deposit = _deposit(status="verified")
    res = _run()
    assert res.exit_code == 0, res.output
    assert not any(c[0] == "POST" and c[1].endswith("/verify") for c in _WalletClient.calls)
    assert any(c[0] == "POST" and c[1].endswith("/complete") for c in _WalletClient.calls)


def test_completed_deposit_is_not_mintable(harness):
    _WalletClient.deposit = _deposit(status="completed")
    res = _run()
    assert res.exit_code != 0
    assert "not mintable" in res.output


# --- #2546: sealed confirmation before /complete; mempool-aware nonce ---


def test_complete_waits_for_sealed_confirmation(harness, monkeypatch):
    # The tx answers 'pending' until the third poll, then confirms.
    polls = {"n": 0}

    def tx_get(url, **kw):
        if "/rpc/transaction/" in url:
            polls["n"] += 1
            if polls["n"] < 3:
                return httpx.Response(200, json={"tx_hash": SEALED_TX, "state": "pending"})
            return httpx.Response(200, json={"status": "confirmed", "block_height": 100})
        return harness.get(url)

    monkeypatch.setattr(httpx, "get", tx_get)
    res = _run()
    assert res.exit_code == 0, res.output
    assert polls["n"] >= 3
    order = [c[1] for c in _WalletClient.calls if c[0] == "POST"]
    assert order[-1].endswith("/complete")


def test_unsealed_timeout_leaves_deposit_uncompleted(harness, monkeypatch):
    harness.tx_status.pop(SEALED_TX)  # stays 'pending' forever
    monkeypatch.setattr(ex, "_MINT_SEAL_TIMEOUT_SECONDS", 0.0)
    monkeypatch.setattr(ex, "_MINT_SEAL_POLL_SECONDS", 0.0)
    res = _run()
    assert res.exit_code != 0
    assert "did not seal" in res.output
    assert not any(c[1].endswith("/complete") for c in _WalletClient.calls)


def test_nonce_advances_past_pending_mempool_slots(harness, monkeypatch):
    # Prior treasury txs occupy pending nonces 5-7; sealed is 5.
    # The new transfer must sign nonce 8, not the colliding sealed 5.
    # pending_nonce_floor probes /rpc/mempool through AITBCHTTPClient on
    # the chain base_url — teach the fake to answer sender pending nonces.
    def client_get(self, endpoint, params=None, headers=None):
        _WalletClient.calls.append(("GET", endpoint))
        if endpoint.startswith("/rpc/mempool"):
            txs = [{"from": TREASURY, "nonce": n, "payload": {}} for n in self.mempool_nonces]
            return {"success": True, "transactions": txs, "count": len(txs)}
        if endpoint.startswith("/rpc/"):
            return {"success": True, "transactions": [], "count": 0}
        assert endpoint == f"/v1/exchange/deposits/{DEPOSIT_ID}"
        return type(self).deposit

    monkeypatch.setattr(_WalletClient, "get", client_get)
    monkeypatch.setattr(_WalletClient, "mempool_nonces", [5, 6, 7], raising=False)
    res = _run()
    assert res.exit_code == 0, res.output
    tx = _posts(harness)[0]["json"]
    assert tx["nonce"] == 8


# --- resume dedup: never pay twice for the same deposit ------------------


def test_resumed_run_adopts_sealed_prior_transfer(harness):
    _WalletClient.deposit = _deposit(status="verified")
    harness.sealed_txs = [
        {
            "tx_hash": SEALED_TX,
            "type": "TRANSFER",
            "sender": TREASURY,
            "payload": {"deposit_id": DEPOSIT_ID, "amount": 1},
        }
    ]
    res = _run()
    assert res.exit_code == 0, res.output
    # No second transfer was submitted.
    assert not _posts(harness)
    assert _WalletClient.complete_body == {"tx_hash": SEALED_TX}


def test_resumed_run_waits_out_pending_prior_transfer(harness, monkeypatch):
    _WalletClient.deposit = _deposit(status="verified")
    # First dedup scan sees the tx pending in the mempool; by the second
    # scan it has sealed — the run adopts it instead of resubmitting.
    scans = {"n": 0}
    pending = [{"from": TREASURY, "payload": {"deposit_id": DEPOSIT_ID}}]
    orig_get = harness.get

    def routed(url, **kw):
        if "/rpc/transactions" in url:
            scans["n"] += 1
            if scans["n"] == 1:
                return httpx.Response(200, json=[])
            return httpx.Response(
                200,
                json=[
                    {
                        "tx_hash": SEALED_TX,
                        "type": "TRANSFER",
                        "sender": TREASURY,
                        "payload": {"deposit_id": DEPOSIT_ID},
                    }
                ],
            )
        if "/rpc/mempool" in url:
            return httpx.Response(200, json={"success": True, "transactions": pending, "count": len(pending)})
        return orig_get(url)

    monkeypatch.setattr(httpx, "get", routed)
    monkeypatch.setattr(ex, "_MINT_SEAL_POLL_SECONDS", 0.0)
    res = _run()
    assert res.exit_code == 0, res.output
    assert scans["n"] >= 2
    assert not _posts(harness)
