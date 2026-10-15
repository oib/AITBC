"""Tests for `aitbc exchange prepay deposit` (PREPAY-1).

Covers the tag contract with the deposit monitor's parser, --print's
no-key guarantee, the Sepolia/registry/cap refusals, and the single
sign+broadcast of --send — all against fakes: no fleet wallet, no real
RPC, no password files.
"""

import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

# The tag round-trip imports wallet_app.bridge.bridge_monitor; that chain
# instantiates aitbc.auth's APIKeyManager (FileLock on /var/lib/aitbc) and
# wallet_app.settings (COORDINATOR_API_KEY required). Redirect both before
# those modules can be imported — read at their import time, so top of file
# is early enough.
os.environ.setdefault(
    "API_KEY_STORAGE_PATH",
    os.path.join(tempfile.mkdtemp(prefix="aitbc-apikeys-"), "api_keys.json"),
)
os.environ.setdefault("COORDINATOR_API_KEY", "test-coordinator-key")
# Some dev shells leak DEBUG=<release|dev>; pydantic-settings parses it as
# bool for wallet_app.Settings. Normalize only values it can't read.
if os.getenv("DEBUG", "").strip().lower() not in ("", "1", "0", "true", "false", "yes", "no", "on", "off"):
    os.environ["DEBUG"] = "false"

import pytest
from click.testing import CliRunner
from eth_account import Account

from aitbc_cli.commands.exchange import prepay as prepay_mod
from aitbc_cli.commands.exchange.prepay import (
    _prepay_data_hex,
    _prepay_tag,
    _short,
    deposit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WALLET_SRC = REPO_ROOT / "apps" / "wallet" / "src"

BUYER = Account.create()
BRIDGE_DEPOSIT = "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"


class FakeExchange:
    """Answers the two exchange reads the command needs."""

    def __init__(self, *_a, node_status="registered", eth_address="MATCH", **_kw):
        self._node_status = node_status
        self._eth_address = eth_address

    def get(self, path):
        if path == "/v1/bridge/status":
            return {"deposit_address": BRIDGE_DEPOSIT}
        if path == "/api/exchange/nodes":
            return {
                "nodes": [
                    {
                        "address": _short(BUYER.address),
                        "status": self._node_status,
                        "eth_address": _short(BUYER.address) if self._eth_address == "MATCH" else self._eth_address,
                    }
                ]
            }
        raise AssertionError(f"unexpected GET {path}")


def _fake_rpc(result_by_method):
    """A _rpc_try/_rpc_call-shaped fake serving method->result from a table."""

    def _call(_ctx, _url, method, params):
        value = result_by_method.get(method)
        return value(method, params) if callable(value) else value

    return _call


BASE_RPC = {
    "eth_chainId": hex(11155111),
    "eth_getTransactionCount": hex(7),
    "eth_gasPrice": hex(2_000_000_000),
    "eth_estimateGas": hex(50_000),
    "eth_getBalance": hex(10**18),
}


@pytest.fixture()
def ctx_fakes(monkeypatch):
    """Patch the wallet resolver, the exchange client, and the JSON-RPC layer."""
    monkeypatch.setattr(
        prepay_mod,
        "_fund_wallet_address",
        lambda ctx, wallet: (BUYER.address, "test-wallet", Path("/tmp/test-wallet.json")),
    )
    monkeypatch.setattr("aitbc_cli.commands.exchange.hub_orders.AITBCHTTPClient", FakeExchange)


def _with_rpc(result_by_method):
    return _fake_rpc(result_by_method)


@pytest.fixture()
def rpc_fn(monkeypatch):
    """Per-test RPC tables: set _rpc_try/_rpc_call from a method->result map."""

    def apply(table):
        fake = _with_rpc(table)
        monkeypatch.setattr(prepay_mod, "_rpc_try", fake)
        monkeypatch.setattr(prepay_mod, "_rpc_call", fake)

    return apply


class TestTagFormat:
    def test_tag_round_trips_through_the_monitors_parser(self):
        if str(WALLET_SRC) not in sys.path:
            sys.path.insert(0, str(WALLET_SRC))
        from wallet_app.bridge.bridge_monitor import _parse_exchange_deposit_tag

        data_hex = _prepay_data_hex(_prepay_tag(BUYER.address))
        assert _parse_exchange_deposit_tag(data_hex) == BUYER.address

    def test_tag_is_utf8_exchange_deposit_prefix(self):
        tag = _prepay_tag(BUYER.address)
        assert tag == f"EXCHANGE_DEPOSIT:{BUYER.address}"
        assert _prepay_data_hex(tag) == "0x" + tag.encode("utf-8").hex()


class TestPrint:
    def test_print_reads_no_key_material(self, ctx_fakes, rpc_fn, monkeypatch):
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.prepay.resolve_wallet_password",
            lambda *a, **k: pytest.fail("password resolved under --print"),
        )
        monkeypatch.setattr(
            "aitbc_cli.commands.wallet._load_wallet",
            lambda *a, **k: pytest.fail("wallet decrypted under --print"),
        )
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code == 0, result.output
        assert "EXCHANGE_DEPOSIT:" in result.output
        assert "0.0002" in result.output

    def test_print_works_without_any_rpc(self, ctx_fakes, rpc_fn):
        rpc_fn({m: Exception("down") for m in BASE_RPC})
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        # _rpc_try degrades to None fields; the unsigned tx still prints.
        assert result.exit_code == 0, result.output


class TestRefusals:
    def test_wrong_chain_id_refuses(self, ctx_fakes, rpc_fn):
        rpc_fn({**BASE_RPC, "eth_chainId": hex(1)})
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "not Sepolia" in result.output

    def test_unregistered_wallet_refuses(self, monkeypatch, rpc_fn):
        monkeypatch.setattr(
            prepay_mod,
            "_fund_wallet_address",
            lambda ctx, wallet: (BUYER.address, "test-wallet", Path("/tmp/test-wallet.json")),
        )
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.AITBCHTTPClient", lambda *a, **k: FakeExchange(node_status="seeded")
        )
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "not 'registered'" in result.output

    def test_eth_address_mismatch_refuses(self, monkeypatch, rpc_fn):
        monkeypatch.setattr(
            prepay_mod,
            "_fund_wallet_address",
            lambda ctx, wallet: (BUYER.address, "test-wallet", Path("/tmp/test-wallet.json")),
        )
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.AITBCHTTPClient",
            lambda *a, **k: FakeExchange(eth_address=_short(Account.create().address)),
        )
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "does not match" in result.output

    def test_missing_registry_row_refuses(self, monkeypatch, rpc_fn):
        monkeypatch.setattr(
            prepay_mod,
            "_fund_wallet_address",
            lambda ctx, wallet: (BUYER.address, "test-wallet", Path("/tmp/test-wallet.json")),
        )
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.hub_orders.AITBCHTTPClient",
            lambda *a, **k: FakeExchange(node_status="registered", eth_address="MATCH"),
        )
        rpc_fn(BASE_RPC)

        # FakeExchange returns a matching row, so force an empty board:
        class Empty(FakeExchange):
            def get(self, path):
                if path == "/api/exchange/nodes":
                    return {"nodes": []}
                return super().get(path)

        monkeypatch.setattr("aitbc_cli.commands.exchange.hub_orders.AITBCHTTPClient", lambda *a, **k: Empty())
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "no row" in result.output


class TestCap:
    def test_over_cap_refuses_and_names_the_flag(self, ctx_fakes, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.02",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "--max-eth" in result.output
        assert "0.01" in result.output

    def test_over_default_cap_passes_with_max_eth(self, ctx_fakes, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.02",
                "--max-eth",
                "0.05",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code == 0, result.output
        assert "0.05" in result.output


class FakeRawBroadcast:
    """Captures the single eth_sendRawTransaction the --send path issues."""

    def __init__(self):
        self.calls = []

    async def post(self, _url, json=None, **_kw):
        assert json["method"] == "eth_sendRawTransaction"
        self.calls.append(json["params"][0])
        return _Resp()


class _Resp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"jsonrpc": "2.0", "result": "0x" + "ab" * 32, "id": 1}


class _AsyncClientCtx:
    def __init__(self, sink):
        self._sink = sink

    async def __aenter__(self):
        return self._sink

    async def __aexit__(self, *exc):
        return False


class TestSend:
    def test_send_signs_and_broadcasts_once(self, ctx_fakes, rpc_fn, monkeypatch):
        rpc_fn(BASE_RPC)
        monkeypatch.setattr(
            "aitbc_cli.commands.exchange.prepay.resolve_wallet_password",
            lambda *a, **k: "test-password",
        )
        monkeypatch.setattr(
            "aitbc_cli.commands.wallet._load_wallet",
            lambda *a, **k: {"address": BUYER.address, "private_key": BUYER.key.hex()},
        )
        sink = FakeRawBroadcast()
        # _broadcast imports httpx inside the function — patch the module attr it resolves.
        import httpx as real_httpx

        monkeypatch.setattr(real_httpx, "AsyncClient", lambda *a, **k: _AsyncClientCtx(sink))
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
                "--send",
                "--password",
                "x",
            ],
            obj={},
        )
        assert result.exit_code == 0, result.output
        assert len(sink.calls) == 1
        assert "0xabababab" in result.output
        assert BUYER.key.hex() not in result.output
        # The broadcast carries the tag inside the signed blob.
        assert b"EXCHANGE_DEPOSIT".hex() in sink.calls[0]

    def test_send_refuses_without_gas_price(self, ctx_fakes, rpc_fn):
        rpc_fn({**BASE_RPC, "eth_gasPrice": None})
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--send",
                "--password",
                "x",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "gas price" in result.output

    def test_send_refuses_without_verified_chain(self, ctx_fakes, rpc_fn):
        rpc_fn(dict.fromkeys(BASE_RPC))  # all RPCs silently empty
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
                "--send",
                "--password",
                "x",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "unverified chain" in result.output

    def test_send_refuses_insufficient_balance(self, ctx_fakes, rpc_fn):
        rpc_fn({**BASE_RPC, "eth_getBalance": hex(10**13)})  # 0.00001 ETH
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
                "--send",
                "--password",
                "x",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "insufficient Sepolia ETH" in result.output


class TestGuards:
    """PREPAY-1b: sub-wei amounts refuse, malformed chain id takes the
    missing-result path, the broadcast loop is closed."""

    def test_sub_wei_amount_refuses_print(self, ctx_fakes, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0000000000000000001",  # 1e-19 ETH → 0 wei after the floor
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "below 1 wei" in result.output

    def test_sub_wei_amount_refuses_send(self, ctx_fakes, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0000000000000000001",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
                "--send",
                "--password",
                "x",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "below 1 wei" in result.output

    def test_malformed_chain_id_print_reports_unverified(self, ctx_fakes, rpc_fn):
        rpc_fn({**BASE_RPC, "eth_chainId": "0xNOT-A-CHAIN"})
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code == 0, result.output
        assert "chain_id_verified" in result.output
        assert "False" in result.output

    def test_malformed_chain_id_send_refuses(self, ctx_fakes, rpc_fn):
        rpc_fn({**BASE_RPC, "eth_chainId": "0xNOT-A-CHAIN"})
        result = CliRunner().invoke(
            deposit,
            [
                "--amount-eth",
                "0.0002",
                "--wallet",
                "test",
                "--exchange-url",
                "http://exchange.test",
                "--eth-rpc-url",
                "http://rpc.test",
                "--send",
                "--password",
                "x",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "unverified chain" in result.output


class TestHelpers:
    def test_short_matches_exchange_form(self):
        assert _short("0xF1C83cd90e4d33F35BE73Dd57CaBa21Ea52D4584") == "0xF1C8…4584"
        assert _short(None) is None
        assert _short("0xabc") == "0xabc"

    def test_eth_amount_to_wei_exact(self):
        # Decimal math, never float — the dust boundary is the point.
        assert Decimal("0.0002") * Decimal(10**18) == 200000000000000


class TestEthRpcResolution:
    """ETH-10c: _eth_rpc resolves ETH_RPC_URL from the node env files
    (/etc/aitbc/*.env via _cli_env_files), not only the process env or the
    --eth-rpc-url flag — nodes keep the value in exchange.env."""

    def _isolate(self, tmp_path, monkeypatch, env_values: dict | None = None):
        """Cut the config layer off the host: no real config file, and the
        env-file list becomes a single tmp file we control."""
        monkeypatch.delenv("ETH_RPC_URL", raising=False)
        monkeypatch.setenv("AITBC_CONFIG_FILE", str(tmp_path / "absent.yaml"))
        if env_values is None:
            monkeypatch.setattr("aitbc_cli.config._cli_env_files", list)
        else:
            env_file = tmp_path / "exchange.env"
            env_file.write_text("".join(f"{k}={v}\n" for k, v in env_values.items()))
            monkeypatch.setattr("aitbc_cli.config._cli_env_files", lambda: [str(env_file)])

    def test_env_file_value_resolves(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch, {"ETH_RPC_URL": "https://envfile.invalid/rpc"})
        assert prepay_mod._eth_rpc(None, None) == "https://envfile.invalid/rpc"

    def test_process_env_wins_over_env_file(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch, {"ETH_RPC_URL": "https://envfile.invalid/rpc"})
        monkeypatch.setenv("ETH_RPC_URL", "https://processenv.invalid/")
        assert prepay_mod._eth_rpc(None, None) == "https://processenv.invalid/"

    def test_explicit_flag_wins(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch, {"ETH_RPC_URL": "https://envfile.invalid/rpc"})
        monkeypatch.setenv("ETH_RPC_URL", "https://processenv.invalid/")
        assert prepay_mod._eth_rpc(None, "https://flag.invalid/") == "https://flag.invalid/"

    def test_absent_value_still_aborts(self, tmp_path, monkeypatch):
        from aitbc_cli.utils.error_handling import CLIError

        self._isolate(tmp_path, monkeypatch)
        with pytest.raises(CLIError) as exc:
            prepay_mod._eth_rpc(None, None)
        assert "Sepolia RPC unresolved" in str(exc.value)
