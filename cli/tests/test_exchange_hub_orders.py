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
from aitbc_cli.utils.http_client import NetworkError


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

    def test_chain_id_probe_uses_root_base(self, monkeypatch):
        """An /rpc-suffixed endpoint probes <root>/rpc/proposer then <root>/health — never /rpc/rpc/…"""
        from aitbc_cli.commands.exchange.hub_orders import _envelope_chain_id

        monkeypatch.delenv("CHAIN_ID", raising=False)
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.get_rpc_endpoint",
            lambda: "https://hub.example/rpc",
        )
        created: list[str] = []
        gets: list[str] = []

        class _Prober:
            def __init__(self, base_url=None, **kw):
                created.append(base_url)

            def get(self, path, **kw):
                gets.append(path)
                if path == "/rpc/proposer":
                    raise NetworkError("404")
                return {"chain_id": "ait-probed"}

        monkeypatch.setattr("aitbc_cli.utils.chain_id.AITBCHTTPClient", _Prober)
        assert _envelope_chain_id(None, None) == "ait-probed"
        assert created == ["https://hub.example"]
        assert gets == ["/rpc/proposer", "/health"]
        assert all("/rpc/rpc" not in f"{b}{p}" for b in created for p in gets)

    def test_chain_id_falls_back_to_island_creds(self, monkeypatch):
        """Probe failure falls back to the credentials' island_chain_id."""
        from aitbc_cli.commands.exchange.hub_orders import _envelope_chain_id

        monkeypatch.delenv("CHAIN_ID", raising=False)
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.get_rpc_endpoint",
            lambda: "https://hub.example/rpc",
        )

        class _FailProber:
            def __init__(self, **kw):
                pass

            def get(self, *a, **k):
                raise NetworkError("unreachable")

        monkeypatch.setattr("aitbc_cli.utils.chain_id.AITBCHTTPClient", _FailProber)
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.get_island_chain_id",
            lambda: "ait-creds-chain",
        )
        assert _envelope_chain_id(None, None) == "ait-creds-chain"

    def test_chain_id_aborts_when_nothing_resolves(self, monkeypatch):
        """Probe failure + no creds island_chain_id → the fail-closed abort."""
        from aitbc_cli.commands.exchange.hub_orders import _envelope_chain_id

        monkeypatch.delenv("CHAIN_ID", raising=False)
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.get_rpc_endpoint",
            lambda: "https://hub.example/rpc",
        )

        class _FailProber:
            def __init__(self, **kw):
                pass

            def get(self, *a, **k):
                raise NetworkError("unreachable")

        monkeypatch.setattr("aitbc_cli.utils.chain_id.AITBCHTTPClient", _FailProber)
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.get_island_chain_id",
            MagicMock(side_effect=FileNotFoundError("no creds file")),
        )
        ctx = MagicMock()
        ctx.obj = {"output_format": "table"}
        with pytest.raises(CLIError):
            _envelope_chain_id(ctx, None)

    def test_chain_id_env_wins_without_probe(self, monkeypatch):
        """CHAIN_ID env resolves before any probing — no HTTP client is built."""
        from aitbc_cli.commands.exchange.hub_orders import _envelope_chain_id

        monkeypatch.setenv("CHAIN_ID", "ait-env-chain")
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.get_rpc_endpoint",
            lambda: "https://hub.example/rpc",
        )
        prober_cls = MagicMock()
        monkeypatch.setattr("aitbc_cli.utils.chain_id.AITBCHTTPClient", prober_cls)
        assert _envelope_chain_id(None, None) == "ait-env-chain"
        prober_cls.assert_not_called()


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

    def test_unfunded_buy_prints_prepay_hint(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = {**self._merge(_head_response(1000), _registered_doc(wallet_key[0], nonce=1))}
        mock_client.post_responses = {
            "default": {
                "id": 9,
                "status": "open",
                "funded_state": "unfunded",
                "funding": {
                    "type": "eth_prepay",
                    "state": "unfunded",
                    "needed_eth": "0.00083",
                    "tag": f"EXCHANGE_DEPOSIT:{wallet_key[0]}",
                    "bridge_eth_address": "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
                },
            }
        }
        result = self._invoke(runner, ["--side", "BUY"])
        assert result.exit_code == 0, result.output
        assert "To fund: send 0.00083 ETH" in result.output
        assert "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359" in result.output

    def test_unfunded_sell_prints_lock_hint(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = {**self._merge(_head_response(1000), _registered_doc(wallet_key[0], nonce=1))}
        mock_client.post_responses = {
            "default": {
                "id": 9,
                "status": "open",
                "funded_state": "unfunded",
                "funding": {
                    "type": "ait_lock",
                    "state": "unfunded",
                    "escrow": "0x52908400098527886E0F7030069857D2E4169EE7",
                    "payload": "sell_quote=9",
                    "required_ait": "10",
                },
            }
        }
        result = self._invoke(runner)
        assert result.exit_code == 0, result.output
        assert "To fund: send a TRANSFER of at least 10 AIT" in result.output
        assert "sell_quote=9" in result.output

    def test_no_hint_without_funding_key(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        # Flag-off response — plain order row, no funding block: nothing
        # extra is printed (byte-identical to the pre-phase-3 CLI output).
        mock_client.get_responses = {**self._merge(_head_response(1000), _registered_doc(wallet_key[0], nonce=1))}
        mock_client.post_responses = {"default": {"id": 9, "status": "open", "funded_state": "unfunded"}}
        result = self._invoke(runner)
        assert result.exit_code == 0, result.output
        assert "To fund:" not in result.output

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

    def test_wallet_path_encrypted_file_no_password(
        self, runner, mock_client, mock_wallet, mock_chain, wallet_key, tmp_path, monkeypatch
    ):
        """CLEAN-1: ``order my --wallet`` reads the plaintext ``address`` field
        of an encrypted wallet file — it must never touch key material, so no
        password source is needed at all (the D4 live find: the command is
        documented 'address only — no signing' yet demanded a password path
        for encrypted wallets)."""
        addr = wallet_key[0]
        wallet_file = tmp_path / "testwallet.json"
        wallet_file.write_text(json.dumps({"encrypted": True, "address": addr, "private_key": "ciphertext"}))
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.find_wallet_file",
            lambda name: wallet_file if name == "testwallet" else None,
        )
        for var in ("AITBC_WALLET_PASSWORD", "AITBC_WALLET_PASSWORD_TESTWALLET"):
            monkeypatch.delenv(var, raising=False)
        mock_client.get_responses = _registered_doc(addr)
        result = runner.invoke(
            order,
            ["my", "--wallet", "testwallet", "--exchange-url", "http://e.invalid"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["address"] == addr
        # No key-material loader was invoked at all — stronger than
        # require_private_key=False, which still resolved a password.
        assert mock_wallet == []


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


# --- order fund (CLI-1, mocks only — no live exchange/wallet/chain) ---------


def _unfunded_sell_doc(addr, order_id=42, required="10", escrow="0x52908400098527886E0F7030069857D2E4169EE7", nonce=0):
    return {
        "/api/exchange/my-orders": {
            "address": addr,
            "label": "node2",
            "registered": True,
            "next_nonce": nonce,
            "orders": [
                {
                    "id": order_id,
                    "order_type": "SELL",
                    "status": "open",
                    "funded_state": "unfunded",
                    "funding": {
                        "type": "ait_lock",
                        "state": "unfunded",
                        "escrow": escrow,
                        "payload": f"sell_quote={order_id}",
                        "required_ait": required,
                    },
                }
            ],
        }
    }


@pytest.fixture
def mock_send():
    """The chain send + password resolution — must never fire without consent."""
    calls = []
    with (
        patch("aitbc_cli.commands.exchange.hub_orders._send_transaction_impl") as send,
        patch("aitbc_cli.commands.exchange.hub_orders.resolve_wallet_password", return_value="pw") as pw,
    ):
        send.return_value = "0x" + "aa" * 32

        def _record(*args, **kwargs):
            calls.append((args, kwargs))
            return send.return_value

        send.side_effect = _record
        yield send, pw, calls


@pytest.fixture
def mock_broadcast():
    """CLI-4: patch ONLY the broadcast — password resolution and the wallet
    file read stay real. Returns the ``_send_transaction_impl`` call list."""
    calls = []
    with patch("aitbc_cli.commands.exchange.hub_orders._send_transaction_impl") as send:
        send.return_value = "0x" + "bb" * 32

        def _record(*args, **kwargs):
            calls.append((args, kwargs))
            return send.return_value

        send.side_effect = _record
        yield calls


@pytest.fixture
def wallet_file(tmp_path, monkeypatch, wallet_key):
    """A real unencrypted file wallet — ``order fund`` reads its plaintext
    ``address`` field; nothing mocks the wallet path."""
    wdir = tmp_path / "wallets"
    wdir.mkdir()
    (wdir / "testwallet.json").write_text(
        json.dumps({"wallet_id": "testwallet", "address": wallet_key[0], "private_key": wallet_key[1]})
    )
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wdir))
    return wdir


@pytest.fixture
def enc_wallet(tmp_path, monkeypatch):
    """A REAL encrypted file wallet — written through ``_save_wallet`` (the
    wallet command's own encrypt_value path), no hand-rolled blob."""
    from aitbc_cli.commands.wallet import _save_wallet

    acct = Account.create()
    wdir = tmp_path / "wallets"
    wdir.mkdir()
    _save_wallet(
        wdir / "encwallet.json",
        {"wallet_id": "encwallet", "address": acct.address, "private_key": acct.key.hex()},
        password="test-pass-1",
    )
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wdir))
    monkeypatch.delenv("AITBC_WALLET_PASSWORD", raising=False)
    monkeypatch.delenv("AITBC_WALLET_PASSWORD_FILE", raising=False)
    monkeypatch.delenv("AITBC_WALLET_PASSWORD_ENCWALLET", raising=False)
    return wdir, acct.address


@pytest.fixture
def pw_file(tmp_path):
    """A real password file — mode 600, owned by the test user (required by
    ``_read_password_file``'s ownership/permission checks)."""
    f = tmp_path / "pw.txt"
    f.write_text("test-pass-1\n")
    f.chmod(0o600)
    return f


def _fund_args(order_id=42, extra=None):
    return [
        "fund",
        str(order_id),
        "--wallet",
        "testwallet",
        "--password-file",
        "/x",
        "--exchange-url",
        "http://e.invalid",
    ] + (extra or [])


class TestOrderFund:
    def test_happy_path_sends_lock(self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key):
        send, pw, calls = mock_send
        mock_client.get_responses = _unfunded_sell_doc(wallet_key[0])
        result = runner.invoke(order, _fund_args(), obj={"output_format": "json"})
        assert result.exit_code == 0, result.output
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] == "testwallet"
        assert args[1] == "0x52908400098527886E0F7030069857D2E4169EE7"
        assert args[2] == Decimal("10")  # required_ait verbatim
        assert kwargs["payload"] == {"sell_quote": 42}
        pw.assert_called_once()

    def test_default_fee_is_chain_standard(self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key):
        """CLI-3 item 6: the fee default is DEFAULT_TX_FEE_AIT, not a literal."""
        from aitbc.utils.units import DEFAULT_TX_FEE_AIT

        send, _pw, calls = mock_send
        mock_client.get_responses = _unfunded_sell_doc(wallet_key[0])
        result = runner.invoke(order, _fund_args(), obj={"output_format": "json"})
        assert result.exit_code == 0, result.output
        args, _kwargs = calls[0]
        assert args[3] == DEFAULT_TX_FEE_AIT == Decimal("0.01")

    def test_explicit_fee_wins(self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key):
        send, _pw, calls = mock_send
        mock_client.get_responses = _unfunded_sell_doc(wallet_key[0])
        result = runner.invoke(order, _fund_args(extra=["--fee", "0.5"]), obj={"output_format": "json"})
        assert result.exit_code == 0, result.output
        args, _kwargs = calls[0]
        assert args[3] == Decimal("0.5")

    def test_print_emits_raw_command_without_broadcast(
        self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key
    ):
        send, pw, calls = mock_send
        mock_client.get_responses = _unfunded_sell_doc(wallet_key[0])
        result = runner.invoke(order, _fund_args(extra=["--print"]), obj={"output_format": "json"})
        assert result.exit_code == 0, result.output
        assert not calls
        pw.assert_not_called()
        assert "--from testwallet" in result.output
        assert "sell_quote" in result.output and '"sell_quote": 42' in result.output
        assert "0x52908400098527886E0F7030069857D2E4169EE7" in result.output

    def test_unknown_order_aborts(self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key):
        send, _pw, calls = mock_send
        mock_client.get_responses = _unfunded_sell_doc(wallet_key[0])
        result = runner.invoke(order, _fund_args(order_id=99), obj={"output_format": "json"})
        assert result.exit_code != 0
        assert not calls

    def test_buy_order_refused(self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key):
        send, _pw, calls = mock_send
        doc = _unfunded_sell_doc(wallet_key[0])
        doc["/api/exchange/my-orders"]["orders"][0]["order_type"] = "BUY"
        mock_client.get_responses = doc
        result = runner.invoke(order, _fund_args(), obj={"output_format": "json"})
        assert result.exit_code != 0
        assert "BUY" in result.output
        assert not calls

    def test_funded_order_refused(self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key):
        send, _pw, calls = mock_send
        doc = _unfunded_sell_doc(wallet_key[0])
        doc["/api/exchange/my-orders"]["orders"][0]["funded_state"] = "funded"
        doc["/api/exchange/my-orders"]["orders"][0].pop("funding")
        mock_client.get_responses = doc
        result = runner.invoke(order, _fund_args(), obj={"output_format": "json"})
        assert result.exit_code != 0
        assert not calls

    def test_flag_off_no_funding_block_refused(self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key):
        send, _pw, calls = mock_send
        doc = _unfunded_sell_doc(wallet_key[0])
        doc["/api/exchange/my-orders"]["orders"][0].pop("funding")
        mock_client.get_responses = doc
        result = runner.invoke(order, _fund_args(), obj={"output_format": "json"})
        assert result.exit_code != 0
        assert not calls

    def test_missing_escrow_aborts(self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key):
        send, _pw, calls = mock_send
        mock_client.get_responses = _unfunded_sell_doc(wallet_key[0], escrow="")
        result = runner.invoke(order, _fund_args(), obj={"output_format": "json"})
        assert result.exit_code != 0
        assert not calls

    def test_bad_required_ait_aborts(self, runner, mock_client, wallet_file, mock_chain, mock_send, wallet_key):
        send, _pw, calls = mock_send
        mock_client.get_responses = _unfunded_sell_doc(wallet_key[0], required="abc")
        result = runner.invoke(order, _fund_args(), obj={"output_format": "json"})
        assert result.exit_code != 0
        assert not calls


# --- order fund on a real encrypted wallet (CLI-4) --------------------------


def _enc_fund_args(order_id=42, password_args=None, extra=None):
    return (
        ["fund", str(order_id), "--wallet", "encwallet"]
        + (password_args or [])
        + ["--exchange-url", "http://e.invalid"]
        + (extra or [])
    )


class TestOrderFundEncryptedWallet:
    """CLI-4: a REAL encrypted file wallet (``_save_wallet``/encrypt_value),
    REAL password resolution — only the broadcast and the exchange HTTP
    client are faked. The 15 Oct D1 failure was exactly this shape: the
    loader demanded a password before the funding block was read."""

    def test_password_file_sends_resolved_pw(self, runner, mock_client, mock_chain, enc_wallet, pw_file, mock_broadcast):
        """--password-file reaches the send: resolved once, reused verbatim."""
        _wdir, addr = enc_wallet
        mock_client.get_responses = _unfunded_sell_doc(addr)
        result = runner.invoke(
            order, _enc_fund_args(password_args=["--password-file", str(pw_file)]), obj={"output_format": "json"}
        )
        assert result.exit_code == 0, result.output
        assert len(mock_broadcast) == 1
        args, _kwargs = mock_broadcast[0]
        assert args[0] == "encwallet"
        assert args[4] == "test-pass-1"  # the file's content — resolution was real
        assert args[2] == Decimal("10")

    def test_wrong_password_fails_closed(self, runner, mock_client, mock_chain, enc_wallet, tmp_path):
        """Wrong password: real ``_send_transaction_impl`` runs, its decrypt
        fails before any network, and the command exits nonzero — no hash."""
        _wdir, addr = enc_wallet
        bad = tmp_path / "bad.txt"
        bad.write_text("wrong-pass-1\n")
        bad.chmod(0o600)
        mock_client.get_responses = _unfunded_sell_doc(addr)
        result = runner.invoke(
            order,
            _enc_fund_args(password_args=["--password-file", str(bad)], extra=["--rpc-url", "http://x.invalid"]),
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "ait_tx_hash" not in result.output

    def test_no_password_fails_closed(self, runner, mock_client, mock_chain, enc_wallet, mock_broadcast):
        """Encrypted wallet, no source, no TTY: fails closed, nothing sent."""
        _wdir, addr = enc_wallet
        mock_client.get_responses = _unfunded_sell_doc(addr)
        result = runner.invoke(order, _enc_fund_args(), obj={"output_format": "json"})
        assert result.exit_code != 0
        assert "No wallet password available" in result.output
        assert not mock_broadcast

    def test_print_needs_no_password(self, runner, mock_client, mock_chain, enc_wallet, mock_broadcast):
        """--print on an encrypted wallet: the plaintext ``address`` field is
        enough — no password resolved, no key touched (spec 1b)."""
        _wdir, addr = enc_wallet
        mock_client.get_responses = _unfunded_sell_doc(addr)
        result = runner.invoke(order, _enc_fund_args(extra=["--print"]), obj={"output_format": "json"})
        assert result.exit_code == 0, result.output
        assert "password" not in result.output.lower()
        assert "--from encwallet" in result.output
        assert '"sell_quote": 42' in result.output
        assert not mock_broadcast

    def test_print_with_stdin_never_reads(self, runner, mock_client, mock_chain, enc_wallet, mock_broadcast):
        """--print --password-stdin with EMPTY stdin still succeeds — the
        stdin source is never touched on the print path."""
        _wdir, addr = enc_wallet
        mock_client.get_responses = _unfunded_sell_doc(addr)
        result = runner.invoke(
            order,
            _enc_fund_args(password_args=["--password-stdin"], extra=["--print"]),
            input="",
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        assert "--from encwallet" in result.output
        assert not mock_broadcast

    def test_password_stdin_read_exactly_once(self, runner, mock_client, mock_chain, enc_wallet, mock_broadcast):
        """One line on stdin funds the send. A second readline would return
        '' and abort — success here proves the resolution ran exactly once
        and its value was reused for the broadcast."""
        _wdir, addr = enc_wallet
        mock_client.get_responses = _unfunded_sell_doc(addr)
        result = runner.invoke(
            order, _enc_fund_args(password_args=["--password-stdin"]), input="test-pass-1\n", obj={"output_format": "json"}
        )
        assert result.exit_code == 0, result.output
        assert len(mock_broadcast) == 1
        args, _kwargs = mock_broadcast[0]
        assert args[4] == "test-pass-1"

    def test_unknown_wallet_aborts(self, runner, mock_client, mock_chain, enc_wallet, mock_broadcast):
        """A wallet that exists nowhere still aborts 'not found' before any
        password or order work."""
        result = runner.invoke(
            order,
            ["fund", "42", "--wallet", "ghost", "--exchange-url", "http://e.invalid"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "not found" in result.output
        assert not mock_broadcast


# --- node set-payout (CLI-1) -----------------------------------------------


class TestNodeSetPayout:
    _ETH = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"

    def test_payout_envelope_checksums_and_posts(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        mock_client.get_responses = _registered_doc(wallet_key[0], nonce=4)
        mock_client.post_responses = {
            "default": {
                "address": wallet_key[0],
                "status": "payout_set",
                "eth_address": self._ETH,
                "previous_eth_address": None,
                "next_nonce": 5,
            }
        }
        result = runner.invoke(
            node,
            [
                "set-payout",
                "--eth-address",
                self._ETH.lower(),  # lowercase input is normalized before signing
                "--wallet",
                "testwallet",
                "--password-file",
                "/x",
                "--exchange-url",
                "http://e.invalid",
            ],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        post = mock_client.instances[0].posts[0]
        assert post["path"] == "/api/exchange/nodes/payout"
        env = post["json"]["envelope"]
        assert env == {
            "action": "exchange_set_payout",
            "eth_address": self._ETH,
            "account_nonce": 4,
            "chain_id": "ait-test-chain",
        }
        from eth_utils import keccak

        from aitbc.crypto.signature_recovery import canonical_address, verify_signature

        digest = keccak(json.dumps(env, sort_keys=True, separators=(",", ":")).encode())
        assert verify_signature(digest, post["json"]["signature"], canonical_address(wallet_key[0]))

    def test_bad_eth_address_aborts_before_network(self, runner, mock_client, mock_wallet, mock_chain, wallet_key):
        result = runner.invoke(
            node,
            [
                "set-payout",
                "--eth-address",
                "not-an-address",
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
        assert not mock_client.instances or not mock_client.instances[0].posts


# --- node list (CLI-1) -----------------------------------------------------


class TestNodeList:
    def test_lists_nodes(self, runner, mock_client):
        mock_client.get_responses = {
            "/api/exchange/nodes": {
                "nodes": [
                    {"label": "node2", "address": "0x5290…", "status": "registered", "open_orders": 2},
                    {"label": "node1", "address": "0xab12…", "status": "seeded", "open_orders": 0},
                ]
            }
        }
        result = runner.invoke(node, ["list", "--exchange-url", "http://e.invalid"], obj={"output_format": "json"})
        assert result.exit_code == 0, result.output
        path, _params = mock_client.instances[0].gets[0]
        assert path == "/api/exchange/nodes"
        payload = json.loads(result.output)
        assert [n["label"] for n in payload["nodes"]] == ["node2", "node1"]

    def test_no_wallet_needed(self, runner, mock_client):
        # No mock_wallet fixture: the command must not touch the keystore.
        mock_client.get_responses = {"/api/exchange/nodes": {"nodes": []}}
        result = runner.invoke(node, ["list", "--exchange-url", "http://e.invalid"], obj={"output_format": "json"})
        assert result.exit_code == 0, result.output
