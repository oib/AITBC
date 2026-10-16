"""Tests for `aitbc wallet eth-balance` (ETH-20b).

Covers the read-only guarantee (no decrypt, no password resolution, no
signing — the wallet file's plaintext ``address`` field is the only thing
read), the EIP-55/checksum rule on ``--address``, the exactly-one-selector
contract, RPC resolution failures, RPC errors, and the Sepolia chain-id
refusal. All against fakes: no fleet wallet, no real RPC, no key material.
"""

import json
import os
import tempfile

# The CLI package import chain can touch modules that read env at import
# time; pin the same guards the prepay suite uses before anything imports.
os.environ.setdefault(
    "API_KEY_STORAGE_PATH",
    os.path.join(tempfile.mkdtemp(prefix="aitbc-apikeys-"), "api_keys.json"),
)
os.environ.setdefault("COORDINATOR_API_KEY", "test-coordinator-key")
if os.getenv("DEBUG", "").strip().lower() not in ("", "1", "0", "true", "false", "yes", "no", "on", "off"):
    os.environ["DEBUG"] = "false"

import pytest
from unittest.mock import MagicMock
from click.testing import CliRunner
from eth_account import Account

from aitbc_cli.commands.wallet import eth_balance as eth_balance_mod
from aitbc_cli.commands.wallet import eth_common as eth_common_mod
from aitbc_cli.commands.wallet.eth_balance import eth_balance
from aitbc_cli.commands.wallet.eth_common import SEPOLIA_CHAIN_ID
from aitbc_cli.utils.error_handling import abort

READER = Account.create()
SENTINEL_KEY = "0xfeedfeed" + "00" * 28  # never printed, never decrypted

BASE_RPC = {
    "eth_chainId": hex(SEPOLIA_CHAIN_ID),
    "eth_getBalance": hex(10**18),
    "eth_getTransactionCount": hex(7),
}

JSON_OBJ = {"output_format": "json"}


@pytest.fixture()
def wallet_file(tmp_path):
    """A minimal wallet file: plaintext address plus a sentinel key field
    the command must never read, decrypt or echo."""
    path = tmp_path / "test-wallet.json"
    path.write_text(json.dumps({"address": READER.address, "private_key": SENTINEL_KEY, "encrypted": True}))
    return path


@pytest.fixture()
def rpc_fn(monkeypatch):
    """Per-test RPC tables: substitute ``rpc_call`` in both the command
    module and the shared ``eth_common`` module — the eth_chainId
    cross-check calls the shared copy."""

    def apply(table):
        calls = []

        def fake(ctx, _url, method, params):
            calls.append((method, params))
            value = table.get(method)
            if isinstance(value, Exception):
                abort(ctx, f"EVM RPC {method} refused: {value}")
            return value(method, params) if callable(value) else value

        monkeypatch.setattr(eth_balance_mod, "rpc_call", fake)
        monkeypatch.setattr(eth_common_mod, "rpc_call", fake)
        return calls

    return apply


def _address_argv(*extra):
    return ["--address", READER.address, "--eth-rpc-url", "http://rpc.test", *extra]


class TestHappyPath:
    def test_address_prints_balance_view(self, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_balance, _address_argv(), obj=JSON_OBJ)
        assert result.exit_code == 0, result.output
        view = json.loads(result.output)
        assert view["address"] == READER.address
        assert view["balance_wei"] == 10**18
        assert view["balance_eth"] == "1"
        assert view["nonce"] == 7
        assert view["rpc"] == "http://rpc.test"

    def test_wallet_file_reads_address_field(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_balance,
            ["--wallet", str(wallet_file), "--eth-rpc-url", "http://rpc.test"],
            obj=JSON_OBJ,
        )
        assert result.exit_code == 0, result.output
        view = json.loads(result.output)
        assert view["address"] == READER.address
        assert view["nonce"] == 7

    def test_rpc_calls_use_latest_block_tag(self, rpc_fn):
        calls = rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_balance, _address_argv(), obj=JSON_OBJ)
        assert result.exit_code == 0, result.output
        assert ("eth_getBalance", [READER.address, "latest"]) in calls
        assert ("eth_getTransactionCount", [READER.address, "latest"]) in calls

    def test_wallet_name_via_sign_path(self, wallet_file, rpc_fn):
        """A bare --wallet name resolves through the shared search — here
        the group-resolved wallet_sign_path wins, no real wallet dir."""
        rpc_fn(BASE_RPC)
        obj = {
            "output_format": "json",
            "wallet_name": "test-wallet",
            "wallet_sign_path": str(wallet_file),
        }
        result = CliRunner().invoke(
            eth_balance,
            ["--wallet", "test-wallet", "--eth-rpc-url", "http://rpc.test"],
            obj=obj,
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["address"] == READER.address

    def test_zero_address_is_a_valid_read(self, rpc_fn):
        """The zero-address and self-send gates were eth-send safety only;
        a read of the zero address is legitimate."""
        zero = "0x" + "0" * 40
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_balance,
            ["--address", zero, "--eth-rpc-url", "http://rpc.test"],
            obj=JSON_OBJ,
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["address"] == zero


class TestRefusals:
    def test_bad_address_refuses(self, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_balance,
            ["--address", "0x12345", "--eth-rpc-url", "http://rpc.test"],
            obj={},
        )
        assert result.exit_code != 0
        assert "invalid --address" in result.output

    def test_mixed_case_checksum_failure_refuses(self, rpc_fn):
        rpc_fn(BASE_RPC)
        chars = list(READER.address)
        for i, c in enumerate(chars[2:], start=2):
            if c.isalpha():
                chars[i] = c.swapcase()
                break
        mangled = "".join(chars)
        assert mangled != READER.address
        result = CliRunner().invoke(
            eth_balance,
            ["--address", mangled, "--eth-rpc-url", "http://rpc.test"],
            obj={},
        )
        assert result.exit_code != 0
        assert "checksum" in result.output

    def test_both_selectors_refuse(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_balance,
            [
                "--address",
                READER.address,
                "--wallet",
                str(wallet_file),
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "exactly one" in result.output or "not both" in result.output

    def test_neither_selector_refuses(self, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_balance,
            ["--eth-rpc-url", "http://rpc.test"],
            obj={},
        )
        assert result.exit_code != 0
        assert "required" in result.output

    def test_unresolved_rpc_refuses(self, rpc_fn, monkeypatch):
        rpc_fn(BASE_RPC)
        monkeypatch.delenv("ETH_RPC_URL", raising=False)
        monkeypatch.setattr(
            "aitbc_cli.config.get_config",
            lambda *a, **k: MagicMock(eth_rpc_url=None),
        )
        result = CliRunner().invoke(eth_balance, ["--address", READER.address], obj={})
        assert result.exit_code != 0
        assert "unresolved" in result.output

    def test_rpc_error_is_nonzero_exit(self, rpc_fn):
        rpc_fn({m: RuntimeError("down") for m in BASE_RPC})
        result = CliRunner().invoke(eth_balance, _address_argv(), obj={})
        assert result.exit_code != 0

    def test_non_sepolia_chain_id_refuses(self, rpc_fn):
        rpc_fn({**BASE_RPC, "eth_chainId": hex(1)})
        result = CliRunner().invoke(eth_balance, _address_argv(), obj={})
        assert result.exit_code != 0
        assert "chain id 1" in result.output
        assert "Sepolia" in result.output

    def test_missing_wallet_file_refuses(self, tmp_path, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_balance,
            ["--wallet", str(tmp_path / "nope.json"), "--eth-rpc-url", "http://rpc.test"],
            obj={},
        )
        assert result.exit_code != 0
        assert "not found" in result.output


class TestReadOnlyGuarantee:
    """The wallet leg reads only the plaintext ``address`` field — never
    the key, never a password, never a decryption path."""

    def test_wallet_path_never_touches_private_key(self, wallet_file, rpc_fn, monkeypatch):
        monkeypatch.setattr(
            "aitbc_cli.commands.wallet._load_wallet",
            lambda *a, **k: pytest.fail("wallet decrypted for a balance read"),
        )
        monkeypatch.setattr(
            "aitbc_cli.utils.wallet_secret.resolve_wallet_password",
            lambda *a, **k: pytest.fail("password resolved for a balance read"),
        )
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_balance,
            ["--wallet", str(wallet_file), "--eth-rpc-url", "http://rpc.test"],
            obj=JSON_OBJ,
        )
        assert result.exit_code == 0, result.output
        assert SENTINEL_KEY not in result.output
        assert SENTINEL_KEY not in str(result.exception or "")

    def test_error_output_never_echoes_raw_rpc_url(self, monkeypatch):
        """Provider keys can sit in the RPC path — errors must show only
        the masked display URL. Exercises the real ``rpc_call`` masking by
        failing at the httpx layer."""
        keyed_url = "http://rpc.test/v3/SECRETKEY"

        def fake_post(*a, **k):
            raise RuntimeError(f"boom {keyed_url}")

        monkeypatch.setattr("httpx.post", fake_post)
        result = CliRunner().invoke(
            eth_balance,
            ["--address", READER.address, "--eth-rpc-url", keyed_url],
            obj={},
        )
        assert result.exit_code != 0
        assert "SECRETKEY" not in result.output
