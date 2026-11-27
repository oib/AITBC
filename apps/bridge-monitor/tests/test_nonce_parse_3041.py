"""#3041 (AUDIT-BRIDGE-PAYOUT-NONCE-FABRICATE-1): a 200 account response
missing ``nonce`` must NOT fabricate nonce 0.

Signing a fabricated 0 produces a doomed envelope: the mempool rejects it,
the auto-abandon nonce-slot proof then passes (chain nonce > 0, slot-0
holder is "other"), the row requeues, and the next pass re-signs at 0 —
an unbudgeted loop that gates the serialized payout slot and takes the
whole deposit lane down. Mirrors the #3015 contract from coordinator-api's
``_parse_account_nonce``: only a real non-negative int (bool excluded,
explicit 0 accepted) counts as nonce truth; anything else is malformed.
"""

import os
import sys
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from bridge_monitor.main import BridgeMonitor
from bridge_monitor.rpc_parse import parse_account_balance, parse_account_nonce, parse_uint_field


class _Resp:
    """Minimal httpx.Response stand-in for the account-probe GET."""

    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = "ok" if status_code == 200 else "error"

    def json(self):
        return self._payload


@pytest.fixture
def monitor(tmp_path, monkeypatch):
    """BridgeMonitor with temp DB and stubbed external deps (same shape as
    test_bridge_monitor.py's fixture)."""
    db_path = str(tmp_path / "bridge_deposits.db")
    monkeypatch.setattr("bridge_monitor.storage.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("bridge_monitor.storage.DB_PATH", db_path)
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0x" + "a" * 40)
    monkeypatch.setenv("GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
    monkeypatch.setenv("BRIDGE_MIN_DEPOSIT_AIT", "1")
    monkeypatch.setenv("AITBC_CHAIN_ID", "bc-test")

    with patch("bridge_monitor.main.EthereumRPCClient"), patch("bridge_monitor.main.get_price_oracle"):
        m = BridgeMonitor()
    return m


def _patch_account_get(monkeypatch, payload, status_code: int = 200):
    """Point every ``httpx.get`` at one canned account response."""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(payload, status_code))


MALFORMED_NONCES = [
    pytest.param({"balance": 10**18}, id="missing-key"),
    pytest.param({"nonce": None, "balance": 1}, id="null"),
    pytest.param({"nonce": "7", "balance": 1}, id="string"),
    pytest.param({"nonce": -1, "balance": 1}, id="negative"),
    pytest.param({"nonce": True, "balance": 1}, id="bool"),
    pytest.param({"nonce": 1.5, "balance": 1}, id="float"),
    pytest.param([1, 2, 3], id="non-dict-list"),
    pytest.param("oops", id="non-dict-string"),
    pytest.param(None, id="non-dict-null"),
]


class TestParseUintField:
    """The shared strict parser both nonce and balance reads go through."""

    def test_explicit_zero_is_valid(self):
        assert parse_uint_field({"nonce": 0}, "nonce") == 0
        assert parse_uint_field({"balance": 0}, "balance") == 0

    def test_valid_int(self):
        assert parse_uint_field({"nonce": 7}, "nonce") == 7

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="missing-key"),
            pytest.param({"nonce": None}, id="null"),
            pytest.param({"nonce": "7"}, id="string"),
            pytest.param({"nonce": -1}, id="negative"),
            pytest.param({"nonce": True}, id="bool"),
            pytest.param({"nonce": 2.0}, id="float"),
            pytest.param([], id="non-dict-list"),
            pytest.param("x", id="non-dict-string"),
            pytest.param(None, id="non-dict-null"),
        ],
    )
    def test_malformed_returns_none(self, payload):
        assert parse_uint_field(payload, "nonce") is None

    def test_field_name_is_respected(self):
        assert parse_uint_field({"nonce": 3, "balance": 9}, "balance") == 9


class TestBuildSignedTransferNonce:
    """_build_signed_transfer must refuse to sign on a malformed nonce."""

    def test_missing_nonce_does_not_sign(self, monitor, monkeypatch):
        """The #3041 pin: 200 with no nonce key → no envelope is built.
        Under the old ``.get("nonce", 0)`` this returned a signed tx at
        nonce 0 — this assertion is the mutation catch."""
        _patch_account_get(monkeypatch, {"balance": 10**18, "address": monitor.genesis_wallet_address})
        result = monitor._build_signed_transfer("0x" + "d" * 40, Decimal("1"))
        assert result is None

    @pytest.mark.parametrize("payload", MALFORMED_NONCES)
    def test_malformed_nonce_variants_do_not_sign(self, monitor, monkeypatch, payload):
        _patch_account_get(monkeypatch, payload)
        assert monitor._build_signed_transfer("0x" + "d" * 40, Decimal("1")) is None

    def test_non_200_still_refuses(self, monitor, monkeypatch):
        _patch_account_get(monkeypatch, {"nonce": 5}, status_code=500)
        assert monitor._build_signed_transfer("0x" + "d" * 40, Decimal("1")) is None

    def test_explicit_zero_nonce_signs(self, monitor, monkeypatch):
        """A fresh payout account really is at nonce 0 — must still sign."""
        _patch_account_get(monkeypatch, {"nonce": 0, "balance": 10**18})
        tx = monitor._build_signed_transfer("0x" + "d" * 40, Decimal("1"))
        assert tx is not None
        assert tx["nonce"] == 0
        assert tx["signature"]
        assert tx["type"] == "TRANSFER"

    def test_valid_nonce_signs(self, monitor, monkeypatch):
        _patch_account_get(monkeypatch, {"nonce": 9, "balance": 10**18})
        tx = monitor._build_signed_transfer("0x" + "d" * 40, Decimal("1"))
        assert tx is not None
        assert tx["nonce"] == 9
        assert tx["signature"]

    def test_failure_path_marks_retry_not_silent(self, monitor, monkeypatch, tmp_path):
        """End-to-end through the caller: a malformed nonce must take the
        normal failure path (_mark_for_retry), never persist an envelope."""
        from bridge_monitor.storage import create_deposit, get_deposit

        create_deposit("0x" + "e" * 64, "0", "1", "0x" + "d" * 40)
        _patch_account_get(monkeypatch, {"balance": 10**18})  # no nonce key
        with (
            patch.object(monitor, "_payout_in_flight", return_value=False),
            patch.object(monitor, "_head_height", return_value=100),
        ):
            # Drive the same branch _submit_payout's caller takes.
            ok = monitor._submit_payout(
                "0x" + "e" * 64,
                "0x" + "d" * 40,
                Decimal("1"),
                eth_usd_price="2000",
                ait_usd_price="1",
            )
        assert ok is False
        row = get_deposit("0x" + "e" * 64)
        assert row is not None
        assert not row.get("signed_tx")  # no envelope was persisted


class TestAccountNonceSibling:
    """_account_nonce feeds the abandon proof — malformed must read as
    unreadable (None → refuse), never as a fabricated nonce."""

    def test_valid_nonce(self, monitor, monkeypatch):
        _patch_account_get(monkeypatch, {"nonce": 7, "balance": 1})
        assert monitor._account_nonce("0x" + "b" * 40) == 7

    def test_explicit_zero_nonce(self, monitor, monkeypatch):
        _patch_account_get(monkeypatch, {"nonce": 0, "balance": 1})
        assert monitor._account_nonce("0x" + "b" * 40) == 0

    @pytest.mark.parametrize("payload", MALFORMED_NONCES)
    def test_malformed_returns_none(self, monitor, monkeypatch, payload):
        _patch_account_get(monkeypatch, payload)
        assert monitor._account_nonce("0x" + "b" * 40) is None

    def test_http_error_returns_none(self, monitor, monkeypatch):
        def _boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", _boom)
        assert monitor._account_nonce("0x" + "b" * 40) is None


class TestPayoutWalletBalanceSibling:
    """_payout_wallet_balance feeds the cap/float checks — malformed must
    read as unknown (None), never as a fabricated empty float."""

    def test_valid_balance(self, monitor, monkeypatch):
        _patch_account_get(monkeypatch, {"nonce": 3, "balance": 12345})
        assert monitor._payout_wallet_balance() == 12345

    def test_explicit_zero_balance(self, monitor, monkeypatch):
        """A genuinely empty wallet reports 0 — distinct from unreadable."""
        _patch_account_get(monkeypatch, {"nonce": 3, "balance": 0})
        result = monitor._payout_wallet_balance()
        assert result == 0
        assert result is not None

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"nonce": 3}, id="missing-key"),
            pytest.param({"balance": None}, id="null"),
            pytest.param({"balance": "100"}, id="string"),
            pytest.param({"balance": -5}, id="negative"),
            pytest.param({"balance": True}, id="bool"),
            pytest.param([1], id="non-dict"),
        ],
    )
    def test_malformed_returns_none(self, monitor, monkeypatch, payload):
        _patch_account_get(monkeypatch, payload)
        assert monitor._payout_wallet_balance() is None


class TestParseHelpersConsistency:
    """nonce and balance share one contract — no drift between siblings."""

    def test_nonce_and_balance_parse_identically(self):
        for payload in (
            {"nonce": 0, "balance": 0},
            {"nonce": 4, "balance": 8},
            {"nonce": None, "balance": None},
            {"nonce": "x", "balance": "y"},
            {},
            [],
        ):
            n = parse_account_nonce(payload)
            b = parse_account_balance(payload)
            assert (n is None) == (b is None), f"drift on {payload!r}"
