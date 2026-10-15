"""Tests for the top-level stake/unstake/liquidity-stake commands (GAP-42).

``aitbc stake``, ``aitbc unstake``, and ``aitbc liquidity-stake`` are
ungrouped aliases that delegate to the real wallet-signed implementations in
``aitbc_cli.commands.wallet.staking``. These tests verify the delegation
wires wallet resolution, request signing, and RPC submission correctly, and
that the commands land on the real node endpoints (``/rpc/staking/*``,
``/rpc/transaction``) rather than a simulated path.
"""

import json
import os
import re
import tempfile
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import click
import pytest
import requests
from aitbc.exceptions import NetworkError
from aitbc.utils import ait_to_units
from aitbc_cli.commands.staking import liquidity_stake, stake, unstake
from aitbc_cli.commands.wallet import _resave_wallet


def extract_json_from_output(output):
    """Extract JSON from CLI output that may contain Rich panel markup"""
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
    lines = clean.strip().split("\n")
    json_lines = []
    in_json = False
    brace_depth = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{"):
            in_json = True
        if in_json:
            json_lines.append(stripped)
            brace_depth += stripped.count("{")
            brace_depth -= stripped.count("}")
            if brace_depth == 0:
                break
    return json.loads("\n".join(json_lines))


@pytest.fixture
def temp_wallet():
    """Create temporary wallet file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        wallet_data = {
            "address": "0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d",
            "balance": 100.0,
            "private_key": "a" * 64,
            "transactions": [],
            "created_at": "2024-01-01T00:00:00",
        }
        json.dump(wallet_data, f)
        temp_path = f.name

    yield temp_path

    os.unlink(temp_path)


@pytest.fixture
def mock_rpc():
    """Mock the blockchain RPC endpoints used by the staking paths.

    Patches the HTTP client inside the wallet staking module (where the real
    calls are made) plus the wallet group's config/adapter/chain-id lookups so
    no network or daemon access is needed.
    """
    mock_http_class = MagicMock()
    mock_client = Mock()
    mock_http_class.return_value = mock_client

    state = {
        "active_stakes": [
            {"stake_id": 7, "amount": ait_to_units(50), "locked_until": "2020-01-01T00:00:00+00:00", "status": "active"}
        ]
    }

    def mock_get(path):
        if "/rpc/staking/" in path:
            return {
                "total_staked": sum(s["amount"] for s in state["active_stakes"]),
                "active_stake_count": len(state["active_stakes"]),
                "active_stakes": state["active_stakes"],
            }
        if "/account/" in path:
            return {"balance": ait_to_units(100.0), "nonce": 0}
        return {}

    def mock_post(path, json=None):
        data = json or {}
        if "/rpc/staking/unstake" in path:
            return {
                "stake_id": data.get("stake_id", 7),
                "amount": ait_to_units(50),
                "transaction_hash": "0xunstakehash",
                "status": "withdrawn",
            }
        if "/rpc/staking/stake" in path:
            return {
                "success": True,
                "stake_id": 7,
                "remaining_balance": ait_to_units(50),
                "locked_until": "2030-01-01T00:00:00+00:00",
                "transaction_hash": "0xstakehash",
                "status": "active",
            }
        if "/rpc/transaction" in path:
            return {"transaction_hash": "0xliqhash"}
        return {}

    mock_client.get.side_effect = mock_get
    mock_client.post.side_effect = mock_post

    mock_config = MagicMock()
    mock_config.blockchain_rpc_url = "http://localhost:8202"
    mock_config.wallet_daemon_url = "http://localhost:8108"

    with (
        patch("aitbc_cli.commands.wallet.staking.AITBCHTTPClient", mock_http_class),
        patch("aitbc_cli.commands.wallet.staking.get_config", return_value=mock_config),
        patch("aitbc_cli.commands.wallet.get_config", return_value=mock_config),
        patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="test-chain"),
        patch("aitbc_cli.utils.dual_mode_wallet_adapter.DualModeWalletAdapter", MagicMock()),
    ):
        yield SimpleNamespace(client=mock_client, http_class=mock_http_class, state=state)


class TestResaveWalletGuard:
    """CLEAN-1: a previously-encrypted wallet must never be re-saved
    without its password — that write would dump the plaintext key."""

    def _ctx(self):
        return click.Context(click.Command("test"), obj={})

    def test_encrypted_wallet_without_password_aborts_no_write(self, tmp_path):
        path = tmp_path / "w.json"
        path.write_text(json.dumps({"encrypted": True, "private_key": "ciphertext", "address": "0x0"}))
        before = path.read_text()
        with pytest.raises(click.exceptions.Exit) as exc:
            _resave_wallet(self._ctx(), path, {"encrypted": True, "private_key": "plaintext"}, None)
        assert exc.value.exit_code == 1
        assert path.read_text() == before

    def test_encrypted_wallet_with_password_resaves_encrypted(self, tmp_path):
        path = tmp_path / "w.json"
        data = {"encrypted": True, "private_key": "deadbeef" * 8, "address": "0x0"}
        _resave_wallet(self._ctx(), path, dict(data), "long-enough-password")
        saved = json.loads(path.read_text())
        assert saved["encrypted"] is True
        assert saved["private_key"] != data["private_key"]

    def test_unencrypted_wallet_resaves_plaintext(self, tmp_path):
        path = tmp_path / "w.json"
        data = {"private_key": "deadbeef" * 8, "address": "0x0"}
        _resave_wallet(self._ctx(), path, dict(data), None)
        assert json.loads(path.read_text())["private_key"] == data["private_key"]


class TestBasicResaveGuard:
    """CLEAN-2: ``earn``/``spend`` in wallet/basic.py re-save through the shared
    ``_resave_wallet`` guard. The defect shape is an on-disk-encrypted wallet
    whose loader decrypted the key with an internally-resolved password: the
    caller's ``password`` is None while ``wallet_data`` carries
    ``encrypted: True`` plus the plaintext key. Re-saving must abort, not write.
    """

    @staticmethod
    def _encrypted_file(tmp_path):
        path = tmp_path / "w.json"
        path.write_text(
            json.dumps(
                {"encrypted": True, "private_key": {"ciphertext": "x"}, "address": "0x0", "balance": "100", "transactions": []}
            )
        )
        return path

    @staticmethod
    def _loaded_encrypted():
        """What ``_load_wallet`` returns after decrypting: flag still set, key in plaintext."""
        return {"encrypted": True, "private_key": "ab" * 32, "address": "0x0", "balance": "100", "transactions": []}

    def _patch_loader(self, monkeypatch, loaded):
        monkeypatch.setattr("aitbc_cli.commands.wallet.basic.resolve_wallet_password", lambda *a, **kw: None)
        monkeypatch.setattr("aitbc_cli.commands.wallet.basic._load_wallet", lambda *a, **kw: dict(loaded))

    def test_earn_encrypted_without_resolved_password_aborts_no_write(self, runner, tmp_path, monkeypatch):
        from aitbc_cli.commands.wallet import wallet

        path = self._encrypted_file(tmp_path)
        before = path.read_text()
        self._patch_loader(monkeypatch, self._loaded_encrypted())
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(path), "--chain-id", "test", "earn", "--amount", "1", "--job-id", "j1"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 1, result.output
        assert path.read_text() == before

    def test_spend_encrypted_without_resolved_password_aborts_no_write(self, runner, tmp_path, monkeypatch):
        from aitbc_cli.commands.wallet import wallet

        path = self._encrypted_file(tmp_path)
        before = path.read_text()
        self._patch_loader(monkeypatch, self._loaded_encrypted())
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(path), "--chain-id", "test", "spend", "--amount", "1", "--description", "d"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 1, result.output
        assert path.read_text() == before

    def test_earn_encrypted_with_password_resaves_encrypted(self, runner, tmp_path, monkeypatch):
        from aitbc_cli.commands.wallet import wallet

        path = self._encrypted_file(tmp_path)
        monkeypatch.setattr("aitbc_cli.commands.wallet.basic.resolve_wallet_password", lambda *a, **kw: "pw-long-enough")
        monkeypatch.setattr("aitbc_cli.commands.wallet.basic._load_wallet", lambda *a, **kw: self._loaded_encrypted())
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(path), "--chain-id", "test", "earn", "--amount", "1", "--job-id", "j1"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        saved = json.loads(path.read_text())
        assert saved["encrypted"] is True
        assert isinstance(saved["private_key"], dict)  # re-encrypted blob, not the plaintext


class TestTopLevelStakingCommands:
    """Top-level ``aitbc stake`` / ``unstake`` / ``liquidity-stake``."""

    def test_registered_on_cli_root(self):
        """All three commands exist at the top level of the real CLI."""
        from aitbc_cli.core.main import cli

        assert "stake" in cli.commands
        assert "unstake" in cli.commands
        assert "liquidity-stake" in cli.commands

    def test_stake_posts_signed_request(self, runner, temp_wallet, mock_rpc):
        """`aitbc stake` signs with the wallet key and POSTs /rpc/staking/stake."""
        result = runner.invoke(
            stake,
            ["--wallet-path", temp_wallet, "--amount", "50", "--duration", "30"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        posts = [c for c in mock_rpc.client.post.call_args_list if "/rpc/staking/stake" in c.args[0]]
        assert len(posts) == 1
        payload = posts[0].kwargs["json"]
        assert payload["address"].lower() == "0xdb5247d03ca2e40f3995a583b2c097ab703efd4d"
        assert payload["amount"] == ait_to_units(Decimal("50"))
        assert payload["lock_days"] == 30
        assert payload["chain_id"] == "test-chain"
        assert payload["signature"]  # wallet-signed, not a stub

        data = extract_json_from_output(result.output)
        assert data["stake_id"] == 7
        assert data["transaction_hash"] == "0xstakehash"
        assert data["locked_until"] == "2030-01-01T00:00:00+00:00"

    def test_stake_missing_wallet_errors(self, runner, mock_rpc, tmp_path):
        result = runner.invoke(
            stake,
            ["--wallet-path", str(tmp_path / "nope.json"), "--amount", "5"],
            obj={"output_format": "json"},
        )
        assert "not found" in result.output

    def test_unstake_posts_signed_release(self, runner, temp_wallet, mock_rpc):
        """`aitbc unstake` submits a real STAKE_RELEASE via /rpc/staking/unstake."""
        result = runner.invoke(
            unstake,
            ["--wallet-path", temp_wallet, "--stake-id", "7"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        posts = [c for c in mock_rpc.client.post.call_args_list if "/rpc/staking/unstake" in c.args[0]]
        assert len(posts) == 1
        payload = posts[0].kwargs["json"]
        assert payload["stake_id"] == 7
        assert payload["signature"]

        data = extract_json_from_output(result.output)
        assert str(data["stake_id"]) == "7"
        assert data["transaction_hash"] == "0xunstakehash"
        assert data["status"] == "withdrawn"
        assert data["locked_until"] == "2020-01-01T00:00:00+00:00"

    def test_unstake_reports_still_locked(self, runner, temp_wallet, mock_rpc):
        """A stake inside its lock window is refused locally with the expiry shown."""
        mock_rpc.state["active_stakes"] = [
            {"stake_id": 7, "amount": ait_to_units(50), "locked_until": "2999-01-01T00:00:00+00:00", "status": "active"}
        ]
        result = runner.invoke(
            unstake,
            ["--wallet-path", temp_wallet, "--stake-id", "7"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "still locked until 2999-01-01" in result.output
        # The release transaction must NOT have been submitted.
        posts = [c for c in mock_rpc.client.post.call_args_list if "/rpc/staking/unstake" in c.args[0]]
        assert not posts

    def test_unstake_unknown_stake_id(self, runner, temp_wallet, mock_rpc):
        """A stake the node does not list as active is refused clearly."""
        result = runner.invoke(
            unstake,
            ["--wallet-path", temp_wallet, "--stake-id", "999"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "no active stake 999" in result.output

    def test_unstake_surfaces_node_error_detail(self, runner, temp_wallet, mock_rpc):
        """A 4xx from the node surfaces its `detail` body (e.g. unconfirmed lock)."""
        http_error = requests.HTTPError("409 Client Error: Conflict")
        http_error.response = Mock(
            status_code=409,
            json=lambda: {"detail": "Stake 7 lock is not yet confirmed on-chain; retry once it is included in a block"},
        )
        net_error = NetworkError("POST request failed: 409 Client Error")
        net_error.__cause__ = http_error

        def post(path, json=None):
            if "/rpc/staking/unstake" in path:
                raise net_error
            return {}

        mock_rpc.client.post.side_effect = post
        result = runner.invoke(
            unstake,
            ["--wallet-path", temp_wallet, "--stake-id", "7"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "not yet confirmed on-chain" in result.output

    def test_liquidity_stake_submits_onchain_tx(self, runner, temp_wallet, mock_rpc):
        """`aitbc liquidity-stake` signs and submits a LIQUIDITY_DEPOSIT tx."""
        result = runner.invoke(
            liquidity_stake,
            ["--wallet-path", temp_wallet, "--amount", "25", "--pool", "main", "--lock-days", "7"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        posts = [c for c in mock_rpc.client.post.call_args_list if "/rpc/transaction" in c.args[0]]
        assert len(posts) == 1
        tx = posts[0].kwargs["json"]
        assert tx["type"] == "LIQUIDITY_DEPOSIT"
        assert tx["amount"] == ait_to_units(Decimal("25"))
        assert tx["payload"]["pool_id"] == "main"
        assert tx["payload"]["lock_days"] == 7
        assert tx["signature"]
        assert "nonce" in tx and tx["chain_id"] == "test-chain"

        data = extract_json_from_output(result.output)
        assert data["transaction_hash"] == "0xliqhash"

        # A local liquidity record is cached, backed by the on-chain tx hash.
        with open(temp_wallet) as f:
            wallet_data = json.load(f)
        assert wallet_data["liquidity"][0]["tx_hash"] == "0xliqhash"
        assert wallet_data["liquidity"][0]["status"] == "active"

    def test_rpc_url_override_is_used(self, runner, temp_wallet, mock_rpc):
        """--rpc-url threads through to the RPC client base_url."""
        result = runner.invoke(
            stake,
            ["--wallet-path", temp_wallet, "--rpc-url", "http://node2:9999", "--amount", "10"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        base_urls = [c.kwargs.get("base_url") for c in mock_rpc.http_class.call_args_list]
        assert base_urls and all(u == "http://node2:9999" for u in base_urls)

    def test_wallet_name_resolution(self, runner, mock_rpc, tmp_path, monkeypatch):
        """--wallet-name resolves <AITBC_WALLET_DIR>/<name>.json like `aitbc wallet`."""
        wallet_path = tmp_path / "staker.json"
        wallet_path.write_text(
            json.dumps(
                {
                    "address": "0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d",
                    "balance": 100.0,
                    "private_key": "a" * 64,
                    "transactions": [],
                }
            )
        )
        monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
        result = runner.invoke(
            stake,
            ["--wallet-name", "staker", "--amount", "10"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        data = extract_json_from_output(result.output)
        assert data["wallet"] == "staker"
        assert data["transaction_hash"] == "0xstakehash"

    def test_help_through_root_cli(self, runner):
        """`aitbc stake --help` resolves the lazy command and lists its options."""
        from aitbc_cli.core.main import cli

        with patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="test-chain"):
            result = runner.invoke(cli, ["stake", "--help"])
        assert result.exit_code == 0
        assert "--amount" in result.output
        assert "--duration" in result.output
        assert "--wallet-name" in result.output
