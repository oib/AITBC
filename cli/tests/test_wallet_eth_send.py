"""Tests for `aitbc wallet eth-send` (CLI-8).

Covers the dry-run guarantee (no decrypt, no password resolution, no sign,
no send), every refusal listed in the command contract, the single
sign+broadcast of --confirm — verified by RLP-decoding the raw signed blob
and recovering the sender — and the no-key-material rule. All against
fakes: no fleet wallet, no real RPC, no password files. The test key is
generated ephemeral in-process; it is never persisted.
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
import rlp
from click.testing import CliRunner
from eth_account import Account

from aitbc_cli.commands.wallet import eth_common as eth_common_mod
from aitbc_cli.commands.wallet import eth_send as eth_send_mod
from aitbc_cli.commands.wallet.eth_send import SEPOLIA_CHAIN_ID, eth_send
from aitbc_cli.utils.error_handling import abort

SENDER = Account.create()
RECIPIENT = Account.create()
OTHER = Account.create()

BASE_RPC = {
    "eth_chainId": hex(SEPOLIA_CHAIN_ID),
    "eth_getTransactionCount": hex(7),
    "eth_gasPrice": hex(2_000_000_000),
    "eth_estimateGas": hex(21_000),
    "eth_getBalance": hex(10**18),
}


@pytest.fixture()
def wallet_file(tmp_path):
    """A minimal wallet file: plaintext address; the key field is never
    decrypted by the command (the --confirm tests patch _load_wallet)."""
    path = tmp_path / "test-wallet.json"
    path.write_text(json.dumps({"address": SENDER.address, "private_key": {"encrypted": "stub"}, "encrypted": True}))
    return path


@pytest.fixture()
def rpc_fn(monkeypatch):
    """Per-test RPC tables: replace rpc_call with a method->result map in
    both the command module and shared ``eth_common`` — the eth_chainId
    cross-check calls the shared copy."""

    def apply(table):
        def fake(ctx, _url, method, params):
            value = table.get(method)
            if isinstance(value, Exception):
                abort(ctx, f"EVM RPC {method} refused: {value}")
            return value(method, params) if callable(value) else value

        monkeypatch.setattr(eth_send_mod, "rpc_call", fake)
        monkeypatch.setattr(eth_common_mod, "rpc_call", fake)

    return apply


def _argv(wallet_path, *extra):
    return [
        "--to",
        RECIPIENT.address,
        "--amount-eth",
        "0.005",
        "--chain-id",
        str(SEPOLIA_CHAIN_ID),
        "--wallet",
        str(wallet_path),
        "--eth-rpc-url",
        "http://rpc.test",
        *extra,
    ]


def _argv_to(wallet_path, to=RECIPIENT.address, amount="0.005", *extra):
    return [
        "--to",
        to,
        "--amount-eth",
        amount,
        "--chain-id",
        str(SEPOLIA_CHAIN_ID),
        "--wallet",
        str(wallet_path),
        "--eth-rpc-url",
        "http://rpc.test",
        *extra,
    ]


class TestRefusals:
    @pytest.mark.parametrize("chain_id", [1, 5, 11155112, 17000])
    def test_non_sepolia_chain_id_refuses(self, chain_id, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_send,
            [
                "--to",
                RECIPIENT.address,
                "--amount-eth",
                "0.005",
                "--chain-id",
                str(chain_id),
                "--wallet",
                str(wallet_file),
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "Sepolia-only" in result.output

    def test_zero_address_refuses(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_send,
            [
                "--to",
                "0x0000000000000000000000000000000000000000",
                "--amount-eth",
                "0.005",
                "--chain-id",
                str(SEPOLIA_CHAIN_ID),
                "--wallet",
                str(wallet_file),
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "zero address" in result.output

    def test_self_send_refuses(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_send,
            [
                "--to",
                SENDER.address,
                "--amount-eth",
                "0.005",
                "--chain-id",
                str(SEPOLIA_CHAIN_ID),
                "--wallet",
                str(wallet_file),
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "own address" in result.output

    def test_over_cap_refuses_and_names_the_flag(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_send,
            [
                "--to",
                RECIPIENT.address,
                "--amount-eth",
                "0.2",
                "--chain-id",
                str(SEPOLIA_CHAIN_ID),
                "--wallet",
                str(wallet_file),
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "--max-eth" in result.output

    @pytest.mark.parametrize("bad", ["0", "-0.1"])
    def test_nonpositive_amount_refuses(self, bad, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_send,
            [
                "--to",
                RECIPIENT.address,
                "--amount-eth",
                bad,
                "--chain-id",
                str(SEPOLIA_CHAIN_ID),
                "--wallet",
                str(wallet_file),
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "must be positive" in result.output

    def test_more_than_18_decimals_refuses(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_send,
            [
                "--to",
                RECIPIENT.address,
                "--amount-eth",
                "0.0000000000000000001",
                "--chain-id",
                str(SEPOLIA_CHAIN_ID),
                "--wallet",
                str(wallet_file),
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "18 decimals" in result.output

    def test_bad_checksum_recipient_refuses(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        # Flip the case of one hex letter inside a checksummed address.
        chars = list(RECIPIENT.address)
        for i, c in enumerate(chars[2:], start=2):
            if c.isalpha():
                chars[i] = c.swapcase()
                break
        mangled = "".join(chars)
        assert mangled != RECIPIENT.address
        result = CliRunner().invoke(
            eth_send,
            [
                "--to",
                mangled,
                "--amount-eth",
                "0.005",
                "--chain-id",
                str(SEPOLIA_CHAIN_ID),
                "--wallet",
                str(wallet_file),
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code != 0
        assert "checksum" in result.output

    def test_wait_without_confirm_refuses(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--wait"), obj={})
        assert result.exit_code != 0
        assert "--wait" in result.output

    def test_missing_wallet_file_refuses(self, tmp_path, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_send, _argv(tmp_path / "nope.json"), obj={})
        assert result.exit_code != 0
        assert "not found" in result.output


class TestDryRun:
    def test_prints_unsigned_transfer(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file), obj={})
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert RECIPIENT.address in result.output
        assert "5000000000000000" in result.output  # 0.005 ETH in wei
        assert "7" in result.output  # nonce
        assert "21000" in result.output
        assert "1" in result.output  # balance 1 ETH

    def test_never_decrypts_signs_or_sends(self, wallet_file, rpc_fn, monkeypatch):
        monkeypatch.setattr(
            "aitbc_cli.commands.wallet._load_wallet",
            lambda *a, **k: pytest.fail("wallet decrypted under dry run"),
        )
        monkeypatch.setattr(
            eth_send_mod,
            "broadcast_raw",
            lambda *a, **k: pytest.fail("broadcast attempted under dry run"),
        )
        monkeypatch.setattr(
            "aitbc_cli.utils.wallet_secret.resolve_wallet_password",
            lambda *a, **k: pytest.fail("password resolved under dry run"),
        )
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file), obj={})
        assert result.exit_code == 0, result.output

    def test_one_wei_amount(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(
            eth_send,
            [
                "--to",
                RECIPIENT.address,
                "--amount-eth",
                "0.000000000000000001",
                "--chain-id",
                str(SEPOLIA_CHAIN_ID),
                "--wallet",
                str(wallet_file),
                "--eth-rpc-url",
                "http://rpc.test",
            ],
            obj={},
        )
        assert result.exit_code == 0, result.output
        wei_row = next(line for line in result.output.splitlines() if "value_wei" in line)
        assert wei_row.split("|")[2].strip() == "1"

    def test_rpc_error_is_nonzero_exit(self, wallet_file, rpc_fn):
        rpc_fn({m: RuntimeError("down") for m in BASE_RPC})
        result = CliRunner().invoke(eth_send, _argv(wallet_file), obj={})
        assert result.exit_code != 0


@pytest.fixture()
def broadcast_sink(monkeypatch):
    calls = []

    def _capture(ctx, url, raw, label="ETH transfer"):
        calls.append(raw)
        return "0x" + "ab" * 32

    monkeypatch.setattr(eth_send_mod, "broadcast_raw", _capture)
    monkeypatch.setattr(
        "aitbc_cli.commands.wallet._load_wallet",
        lambda *a, **k: {"address": SENDER.address, "private_key": SENDER.key.hex()},
    )
    return calls


class TestConfirm:
    def test_signs_and_broadcasts_once(self, wallet_file, rpc_fn, broadcast_sink):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "x"), obj={})
        assert result.exit_code == 0, result.output
        assert len(broadcast_sink) == 1
        assert "0xabababab" in result.output
        assert SENDER.key.hex() not in result.output
        raw = broadcast_sink[0]
        assert Account.recover_transaction(raw) == SENDER.address
        fields = rlp.decode(bytes.fromhex(raw[2:]))
        nonce, gas_price, gas_limit, to, value, _data, v, _r, _s = fields
        assert int.from_bytes(nonce, "big") == 7
        assert to == bytes.fromhex(RECIPIENT.address[2:].lower())
        assert int.from_bytes(value, "big") == 5_000_000_000_000_000
        assert (int.from_bytes(v, "big") - 35) // 2 == SEPOLIA_CHAIN_ID
        assert int.from_bytes(gas_limit, "big") == 21_000
        assert int.from_bytes(gas_price, "big") == 2_000_000_000

    def test_insufficient_balance_refuses(self, wallet_file, rpc_fn, broadcast_sink):
        rpc_fn({**BASE_RPC, "eth_getBalance": hex(1)})
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "x"), obj={})
        assert result.exit_code != 0
        assert "insufficient" in result.output
        assert broadcast_sink == []

    def test_key_mismatch_refuses(self, wallet_file, rpc_fn, monkeypatch, broadcast_sink):
        rpc_fn(BASE_RPC)
        monkeypatch.setattr(
            "aitbc_cli.commands.wallet._load_wallet",
            lambda *a, **k: {"address": SENDER.address, "private_key": OTHER.key.hex()},
        )
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "x"), obj={})
        assert result.exit_code != 0
        assert "does not match" in result.output
        assert broadcast_sink == []

    def test_wrong_rpc_chain_refuses_even_with_flag(self, wallet_file, rpc_fn, broadcast_sink):
        rpc_fn({**BASE_RPC, "eth_chainId": hex(1)})
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "x"), obj={})
        assert result.exit_code != 0
        assert "chain id 1" in result.output
        assert broadcast_sink == []

    def test_no_key_or_password_material_in_output(self, wallet_file, rpc_fn, broadcast_sink):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "sup3r-secret-pw"), obj={})
        assert result.exit_code == 0, result.output
        haystack = result.output + str(result.exception or "")
        assert SENDER.key.hex() not in haystack
        assert "sup3r-secret-pw" not in haystack

    def test_wait_prints_receipt(self, wallet_file, rpc_fn, broadcast_sink):
        receipt = {"status": "0x1", "blockNumber": hex(12345), "gasUsed": hex(21000)}
        table = {**BASE_RPC, "eth_getTransactionReceipt": receipt}
        rpc_fn(table)
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "x", "--wait"), obj={})
        assert result.exit_code == 0, result.output
        assert "12345" in result.output
        assert "0x1" in result.output


class TestGasCeiling:
    """CLI-8b: --confirm refuses to sign when eth_gasPrice exceeds
    --max-gas-gwei (default 50); the key is never decrypted."""

    def test_over_ceiling_refuses_before_key_load(self, wallet_file, rpc_fn, monkeypatch):
        broadcasts = []
        monkeypatch.setattr(eth_send_mod, "broadcast_raw", lambda *a, **k: broadcasts.append(a))
        monkeypatch.setattr(
            "aitbc_cli.commands.wallet._load_wallet",
            lambda *a, **k: pytest.fail("wallet decrypted despite over-ceiling gas price"),
        )
        rpc_fn({**BASE_RPC, "eth_gasPrice": hex(100 * 10**9)})
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "x"), obj={})
        assert result.exit_code != 0
        assert "--max-gas-gwei" in result.output
        assert "100" in result.output
        assert broadcasts == []

    def test_raised_ceiling_allows_send(self, wallet_file, rpc_fn, broadcast_sink):
        rpc_fn({**BASE_RPC, "eth_gasPrice": hex(100 * 10**9)})
        result = CliRunner().invoke(
            eth_send,
            _argv(wallet_file, "--confirm", "--password", "x", "--max-gas-gwei", "150"),
            obj={},
        )
        assert result.exit_code == 0, result.output
        assert len(broadcast_sink) == 1
        fields = rlp.decode(bytes.fromhex(broadcast_sink[0][2:]))
        assert int.from_bytes(fields[1], "big") == 100 * 10**9  # gasPrice signed as quoted

    def test_boundary_price_sends(self, wallet_file, rpc_fn, broadcast_sink):
        rpc_fn({**BASE_RPC, "eth_gasPrice": hex(50 * 10**9)})  # == default ceiling
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "x"), obj={})
        assert result.exit_code == 0, result.output
        assert len(broadcast_sink) == 1

    def test_dry_run_marks_over_ceiling_but_prints(self, wallet_file, rpc_fn):
        rpc_fn({**BASE_RPC, "eth_gasPrice": hex(100 * 10**9)})
        result = CliRunner().invoke(eth_send, _argv(wallet_file), obj={})
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "over_gas_ceiling" in result.output

    @pytest.mark.parametrize("bad", ["0", "-1"])
    def test_nonpositive_ceiling_refuses(self, bad, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--max-gas-gwei", bad), obj={})
        assert result.exit_code != 0
        assert "--max-gas-gwei must be positive" in result.output

    def test_sub_wei_ceiling_refuses(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--max-gas-gwei", "0.0000000001"), obj={})
        assert result.exit_code != 0
        assert "9 decimals" in result.output


class TestContractRecipient:
    """TOOL-2: --to is probed with eth_getCode; --confirm refuses contract
    bytecode unless --allow-contract, before the key is decrypted. The dry
    run shows the result either way."""

    CONTRACT_RPC = {**BASE_RPC, "eth_getCode": "0x6080604052"}

    def test_contract_recipient_refuses_before_key_load(self, wallet_file, rpc_fn, monkeypatch):
        broadcasts = []
        monkeypatch.setattr(eth_send_mod, "broadcast_raw", lambda *a, **k: broadcasts.append(a))
        monkeypatch.setattr(
            "aitbc_cli.commands.wallet._load_wallet",
            lambda *a, **k: pytest.fail("wallet decrypted for a contract recipient"),
        )
        rpc_fn(self.CONTRACT_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "x"), obj={})
        assert result.exit_code != 0
        assert "--allow-contract" in result.output
        assert broadcasts == []

    def test_allow_contract_sends(self, wallet_file, rpc_fn, broadcast_sink):
        rpc_fn(self.CONTRACT_RPC)
        result = CliRunner().invoke(
            eth_send,
            _argv(wallet_file, "--confirm", "--password", "x", "--allow-contract"),
            obj={},
        )
        assert result.exit_code == 0, result.output
        assert len(broadcast_sink) == 1

    def test_allow_contract_without_confirm_refuses(self, wallet_file, rpc_fn):
        rpc_fn(BASE_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file, "--allow-contract"), obj={})
        assert result.exit_code != 0
        assert "--allow-contract" in result.output

    def test_dry_run_shows_getcode_result(self, wallet_file, rpc_fn):
        rpc_fn(self.CONTRACT_RPC)
        result = CliRunner().invoke(eth_send, _argv(wallet_file), obj={})
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "to_is_contract" in result.output

    def test_empty_code_is_not_a_contract(self, wallet_file, rpc_fn, broadcast_sink):
        for empty in ("0x", "0x0", ""):
            rpc_fn({**BASE_RPC, "eth_getCode": empty})
            broadcast_sink.clear()
            result = CliRunner().invoke(eth_send, _argv(wallet_file, "--confirm", "--password", "x"), obj={})
            assert result.exit_code == 0, f"{empty!r}: {result.output}"
            assert len(broadcast_sink) == 1
