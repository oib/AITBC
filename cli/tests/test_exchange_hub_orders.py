"""
Unit tests for the hub-exchange signed-order CLI commands (ETH-11 phase 2).

Covers ``aitbc exchange order place|cancel|my`` and
``aitbc exchange node register`` in
``cli/aitbc_cli/commands/exchange/hub_orders.py``.

All keys are throwaway test keys generated inside the test process — no real
wallet, password, mnemonic, or RPC URL is read or printed. The signature
round-trip verifies against the repo's canonical verifier
(``aitbc.crypto.signature_recovery.verify_signature``), which is what the
exchange handler uses — a passing check here means the CLI emits envelopes
the hub accepts.
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from eth_account import Account

from aitbc_cli.commands.exchange.hub_orders import node, order
from aitbc_cli.utils.error_handling import CLIError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def wallet_key():
    """A throwaway secp256k1 key — exists only inside this test process."""
    acct = Account.create()
    return acct.address, acct.key.hex()


@pytest.fixture
def mock_client():
    """Fake AITBCHTTPClient recording calls; per-test canned responses."""

    class FakeClient:
        instances: list = []
        get_responses: dict = {}
        post_responses: dict = {}
        post_error = None
        get_error = None

        def __init__(self, base_url=None, timeout=None, **kw):
            self.base_url = base_url
            self.timeout = timeout
            self.gets = []
            self.posts = []
            FakeClient.instances.append(self)

        def get(self, path, params=None, **kw):
            self.gets.append((path, params))
            if FakeClient.get_error is not None:
                raise FakeClient.get_error
            for key, resp in FakeClient.get_responses.items():
                if key in path:
                    return resp
            return {}

        def post(self, path, json=None, idempotency_key=None, **kw):
            self.posts.append({"path": path, "json": json, "idempotency_key": idempotency_key})
            if FakeClient.post_error is not None:
                raise FakeClient.post_error
            return FakeClient.post_responses.get("default", {"id": 1, "status": "open"})

    FakeClient.instances.clear()
    FakeClient.get_responses = {}
    FakeClient.post_responses = {}
    FakeClient.post_error = None
    FakeClient.get_error = None
    with patch("aitbc_cli.commands.exchange.hub_orders.AITBCHTTPClient", FakeClient):
        yield FakeClient


@pytest.fixture
def mock_wallet(wallet_key):
    """load_wallet_for_payment -> the throwaway key; records call kwargs."""
    calls = []

    def fake_load(ctx, **kwargs):
        calls.append(kwargs)
        return wallet_key[0], wallet_key[1], "testwallet"

    with patch("aitbc_cli.commands.exchange.hub_orders.load_wallet_for_payment", side_effect=fake_load):
        yield calls


@pytest.fixture
def mock_chain(monkeypatch):
    """Local RPC head + island chain_id — no real network."""
    monkeypatch.setattr("aitbc_cli.commands.exchange.hub_orders.get_rpc_endpoint", lambda: "http://test-rpc.invalid")
    monkeypatch.setattr(
        "aitbc_cli.commands.exchange.hub_orders.resolve_chain_id",
        lambda ctx, rpc_url, **kw: "ait-test-chain",
    )


def _head_response(height=1000):
    return {"/head": {"height": height}}


def _registered_doc(addr, nonce=0, label="node2"):
    return {
        "/api/exchange/my-orders": {
            "address": addr,
            "label": label,
            "registered": True,
            "next_nonce": nonce,
            "orders": [{"id": 7, "status": "open"}],
        }
    }


# --- tick conversion -----------------------------------------------------


class TestTicks:
    def test_exact_eight_decimals(self):
        from aitbc_cli.commands.exchange.hub_orders import _to_ticks

        assert _to_ticks(None, Decimal("0.00000001"), "amount") == 1
        assert _to_ticks(None, Decimal("10.5"), "amount") == 1_050_000_000

    def test_rejects_nine_decimals(self, runner):
        from aitbc_cli.commands.exchange.hub_orders import _to_ticks

        ctx = MagicMock()
        ctx.obj = {"output_format": "table"}
        with pytest.raises(CLIError):
            _to_ticks(ctx, Decimal("0.000000001"), "amount")

    def test_large_exact(self):
        from aitbc_cli.commands.exchange.hub_orders import _to_ticks

        assert _to_ticks(None, Decimal("123456.12345678"), "amount") == 12_345_612_345_678


# --- URL + chain-id resolution -------------------------------------------


class TestResolution:
    def test_rpc_url_rejected_as_exchange(self, runner):
        from aitbc_cli.commands.exchange.hub_orders import _exchange_base_url

        ctx = MagicMock()
        ctx.obj = {"output_format": "table"}
        with pytest.raises(CLIError):
            _exchange_base_url(ctx, "http://node:8100/rpc")

    def test_missing_url_aborts(self, runner):
        from aitbc_cli.commands.exchange.hub_orders import _exchange_base_url

        ctx = MagicMock()
        ctx.obj = {"output_format": "table"}
        with patch("aitbc_cli.config.get_config") as gc:
            gc.return_value.exchange_service_url = None
            with pytest.raises(CLIError):
                _exchange_base_url(ctx, None)

    def test_chain_id_override_and_resolution(self, monkeypatch):
        from aitbc_cli.commands.exchange.hub_orders import _envelope_chain_id

        assert _envelope_chain_id(None, "custom-chain") == "custom-chain"
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.get_rpc_endpoint",
            lambda: "http://test-rpc.invalid",
        )
        seen = []

        def _fake_resolve(ctx, rpc_url, **kw):
            seen.append(rpc_url)
            return "resolved-chain"

        monkeypatch.setattr("aitbc_cli.commands.exchange.hub_orders.resolve_chain_id", _fake_resolve)
        assert _envelope_chain_id(None, None) == "resolved-chain"
        assert seen == ["http://test-rpc.invalid"]


# --- order place ----------------------------------------------------------


class TestOrderPlace:
    def _invoke(self, runner, extra=None):
        args = [
            "place",
            "--side",
            "SELL",
            "--amount",
            "10",
            "--price",
            "0.000083",
            "--wallet",
            "testwallet",
            "--password-file",
            "/nonexistent-pw",
            "--exchange-url",
            "http://exchange.invalid",
        ]
        return runner.invoke(order, args + (extra or []), obj={"output_format": "json"})

    def test_signed_place_envelope_and_verification(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = {**self._merge(_head_response(1000), _registered_doc(wallet_key[0], nonce=3))}
        result = self._invoke(runner)
        assert result.exit_code == 0, result.output

        post = mock_client.instances[0].posts[0]
        assert post["path"] == "/api/orders"
        env = post["json"]["envelope"]
        assert env == {
            "side": "SELL",
            "pair": "AIT/ETH",
            "amount_ticks": 1_000_000_000,
            "price_ticks": 8_300,
            "expiry_height": 1000 + 1440,
            "account_nonce": 3,
            "chain_id": "ait-test-chain",
        }
        assert post["json"]["user_address"] == wallet_key[0]
        # The signature doubles as the idempotency key.
        assert post["idempotency_key"] == post["json"]["signature"]
        # Verify with the same primitive + digest the handler uses.
        from eth_utils import keccak

        from aitbc.crypto.signature_recovery import canonical_address, verify_signature

        digest = keccak(json.dumps(env, sort_keys=True, separators=(",", ":")).encode())
        assert verify_signature(digest, post["json"]["signature"], canonical_address(wallet_key[0]))
        # Wallet loaded with private key for signing, via the shared loader.
        assert mock_wallet[0]["require_private_key"] is True

    @staticmethod
    def _merge(*dicts):
        out = {}
        for d in dicts:
            out.update(d)
        return out

    def test_unregistered_node_aborts(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        doc = _registered_doc(wallet_key[0])
        doc["/api/exchange/my-orders"]["registered"] = False
        mock_client.get_responses = {**_head_response(1000), **doc}
        result = self._invoke(runner)
        assert result.exit_code != 0
        assert not mock_client.instances[0].posts  # nothing POSTed

    def test_nine_decimal_amount_aborts_before_network(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = {**_head_response(1000), **_registered_doc(wallet_key[0])}
        result = runner.invoke(
            order,
            [
                "place",
                "--side",
                "BUY",
                "--amount",
                "0.000000001",
                "--price",
                "0.1",
                "--wallet",
                "testwallet",
                "--password-file",
                "/x",
                "--exchange-url",
                "http://exchange.invalid",
            ],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert not mock_client.instances[0].posts

    def test_nonpositive_amount_aborts(self, runner, mock_wallet):
        result = runner.invoke(
            order,
            [
                "place",
                "--side",
                "SELL",
                "--amount",
                "0",
                "--price",
                "0.1",
                "--wallet",
                "w",
                "--password-file",
                "/x",
                "--exchange-url",
                "http://e.invalid",
            ],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0

    def test_chain_id_flag(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = {**_head_response(1000), **_registered_doc(wallet_key[0])}
        result = self._invoke(runner, ["--chain-id", "other-chain"])
        assert result.exit_code == 0, result.output
        env = mock_client.instances[0].posts[0]["json"]["envelope"]
        assert env["chain_id"] == "other-chain"


# --- order cancel ---------------------------------------------------------


class TestOrderCancel:
    def test_cancel_envelope_and_path(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = {**_head_response(500), **_registered_doc(wallet_key[0], nonce=2)}
        mock_client.post_responses = {"default": {"id": 42, "status": "cancelled"}}
        result = runner.invoke(
            order,
            ["cancel", "42", "--wallet", "testwallet", "--password-file", "/x", "--exchange-url", "http://exchange.invalid"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        post = mock_client.instances[0].posts[0]
        assert post["path"] == "/api/orders/42/cancel"
        env = post["json"]["envelope"]
        assert env == {
            "action": "exchange_cancel",
            "order_id": 42,
            "expiry_height": 500 + 120,
            "account_nonce": 2,
            "chain_id": "ait-test-chain",
        }

    def test_expires_in_flag(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = {**_head_response(500), **_registered_doc(wallet_key[0])}
        result = runner.invoke(
            order,
            [
                "cancel",
                "9",
                "--expires-in",
                "30",
                "--wallet",
                "w",
                "--password-file",
                "/x",
                "--exchange-url",
                "http://e.invalid",
            ],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        assert mock_client.instances[0].posts[0]["json"]["envelope"]["expiry_height"] == 530


# --- order my -------------------------------------------------------------


class TestOrderMy:
    def test_address_path_no_wallet(self, runner, mock_client, mock_chain):
        addr = "0x" + "ab" * 20
        mock_client.get_responses = _registered_doc(addr)
        result = runner.invoke(
            order,
            ["my", "--address", addr, "--exchange-url", "http://e.invalid"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        path, params = mock_client.instances[0].gets[0]
        assert path == "/api/exchange/my-orders"
        assert params == {"addr": addr}
        payload = json.loads(result.output)
        assert payload["registered"] is True
        assert payload["orders"] == [{"id": 7, "status": "open"}]

    def test_requires_wallet_or_address(self, runner):
        result = runner.invoke(order, ["my"], obj={"output_format": "json"})
        assert result.exit_code != 0

    def test_wallet_path_no_signing(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = _registered_doc(wallet_key[0])
        result = runner.invoke(
            order,
            ["my", "--wallet", "testwallet", "--exchange-url", "http://e.invalid"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        # Address resolution must NOT request the private key.
        assert mock_wallet[0]["require_private_key"] is False


# --- node register --------------------------------------------------------


class TestNodeRegister:
    def test_register_envelope_and_path(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = _registered_doc(wallet_key[0], nonce=0, label="node2")
        mock_client.get_responses["/api/exchange/my-orders"]["registered"] = False
        mock_client.post_responses = {"default": {"label": "node2", "status": "registered"}}
        result = runner.invoke(
            node,
            ["register", "--wallet", "testwallet", "--password-file", "/x", "--exchange-url", "http://e.invalid"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        post = mock_client.instances[0].posts[0]
        assert post["path"] == "/api/exchange/nodes/register"
        env = post["json"]["envelope"]
        assert env == {
            "action": "exchange_register",
            "address": wallet_key[0],
            "label": "node2",  # default = seeded label
            "account_nonce": 0,
            "chain_id": "ait-test-chain",
        }

    def test_already_registered_skips_post(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = _registered_doc(wallet_key[0], label="node2")
        result = runner.invoke(
            node,
            ["register", "--wallet", "w", "--password-file", "/x", "--exchange-url", "http://e.invalid"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        assert not mock_client.instances[0].posts

    def test_no_seeded_label_aborts(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        doc = _registered_doc(wallet_key[0])
        doc["/api/exchange/my-orders"]["label"] = None
        doc["/api/exchange/my-orders"]["registered"] = False
        mock_client.get_responses = doc
        result = runner.invoke(
            node,
            ["register", "--wallet", "w", "--password-file", "/x", "--exchange-url", "http://e.invalid"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert not mock_client.instances[0].posts


# --- network error surfaces -----------------------------------------------


class TestErrors:
    def test_post_network_error_aborts(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        from aitbc_cli.utils.error_handling import NetworkError

        mock_client.get_responses = {**_head_response(1000), **_registered_doc(wallet_key[0])}
        mock_client.post_error = NetworkError("connection refused")
        result = runner.invoke(
            order,
            [
                "place",
                "--side",
                "BUY",
                "--amount",
                "1",
                "--price",
                "0.1",
                "--wallet",
                "w",
                "--password-file",
                "/x",
                "--exchange-url",
                "http://e.invalid",
            ],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert isinstance(result.exception, NetworkError)

    def test_exchange_down_at_nonce_fetch(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        from aitbc_cli.utils.error_handling import NetworkError

        mock_client.get_responses = _head_response(1000)
        mock_client.get_error = NetworkError("timeout")
        result = runner.invoke(
            order,
            [
                "place",
                "--side",
                "BUY",
                "--amount",
                "1",
                "--price",
                "0.1",
                "--wallet",
                "w",
                "--password-file",
                "/x",
                "--exchange-url",
                "http://e.invalid",
            ],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
