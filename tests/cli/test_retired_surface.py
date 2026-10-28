"""Tests for the BNT-3 retired-surface CLI message (HTTP 410).

The protocol-transfer RPC surfaces (``/rpc/staking/stake``,
``/rpc/staking/unstake``, the ``/rpc/agent-staking/*`` writes and the
``/rpc/bounty/*`` writes) answer HTTP 410 while the v17 payload.auth
revival is unarmed — below ``STATE_TRANSITION_V17_HEIGHT`` a queued
transfer could not seal (see ``docs/design/v9-unsigned-protocol-transfers.md``).
These tests pin the CLI behaviour: a 410 answer prints a clear
``Retired RPC surface:`` message carrying the node's own detail, while every
other error keeps the legacy ``Error staking/unstaking tokens:`` form.
"""

import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
from aitbc.exceptions import NetworkError
from aitbc.utils import ait_to_units
from aitbc_cli.commands.wallet import wallet
from aitbc_cli.utils.http_client import RETIRED_SURFACE_MESSAGE, retired_surface_message

RETIRED_DETAIL = (
    "Staking is retired: protocol-escrow transfers cannot seal at block version 9 "
    "and no transaction would ever confirm. See docs/design/v9-unsigned-protocol-transfers.md."
)


def _network_error(status: int, body: dict | None = None) -> NetworkError:
    """Build a NetworkError wrapping a requests.HTTPError with a mocked response."""
    http_error = requests.HTTPError(f"{status} Client Error")
    http_error.response = Mock(status_code=status, json=lambda: body or {})
    err = NetworkError(f"POST request failed: {status} Client Error")
    err.__cause__ = http_error
    return err


class TestRetiredSurfaceMessage:
    """Helper-level pins for ``retired_surface_message``."""

    def test_returns_server_detail_on_410(self):
        err = _network_error(410, {"detail": RETIRED_DETAIL})
        assert retired_surface_message(err) == RETIRED_DETAIL

    def test_falls_back_when_410_body_has_no_detail(self):
        err = _network_error(410, {})
        assert retired_surface_message(err) == RETIRED_SURFACE_MESSAGE

    def test_returns_none_for_non_410(self):
        err = _network_error(409, {"detail": "Stake 7 lock is not yet confirmed on-chain"})
        assert retired_surface_message(err) is None

    def test_returns_none_without_response(self):
        assert retired_surface_message(NetworkError("connection refused")) is None


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

    Same patch set as tests/cli/test_commands_staking.py: the HTTP client
    inside the wallet staking module plus the wallet group's
    config/adapter/chain-id lookups.
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

    mock_client.get.side_effect = mock_get
    mock_client.post.return_value = {}

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


class TestWalletStakeRetiredSurface:
    """``aitbc wallet stake`` / ``aitbc wallet unstake`` against a 410 node."""

    def test_wallet_stake_410_prints_retired_message(self, runner, temp_wallet, mock_rpc):
        def post(path, json=None):
            if "/rpc/staking/stake" in path:
                raise _network_error(410, {"detail": RETIRED_DETAIL})
            return {}

        mock_rpc.client.post.side_effect = post
        result = runner.invoke(
            wallet,
            ["--wallet-path", temp_wallet, "stake", "--amount", "50", "--duration", "30"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "Retired RPC surface" in result.output
        assert "retired" in result.output
        assert "Staking is retired" in result.output

    def test_wallet_stake_410_without_detail_uses_fallback(self, runner, temp_wallet, mock_rpc):
        def post(path, json=None):
            if "/rpc/staking/stake" in path:
                raise _network_error(410)
            return {}

        mock_rpc.client.post.side_effect = post
        result = runner.invoke(
            wallet,
            ["--wallet-path", temp_wallet, "stake", "--amount", "50"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "Retired RPC surface" in result.output
        assert "retired since block version 9" in result.output

    def test_wallet_stake_non_410_keeps_legacy_error(self, runner, temp_wallet, mock_rpc):
        """A non-410 failure must not be reported as a retired surface."""
        def post(path, json=None):
            if "/rpc/staking/stake" in path:
                raise _network_error(500, {"detail": "internal boom"})
            return {}

        mock_rpc.client.post.side_effect = post
        result = runner.invoke(
            wallet,
            ["--wallet-path", temp_wallet, "stake", "--amount", "50"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "Error staking tokens:" in result.output
        assert "internal boom" in result.output
        assert "Retired RPC surface" not in result.output

    def test_wallet_unstake_410_prints_retired_message(self, runner, temp_wallet, mock_rpc):
        def post(path, json=None):
            if "/rpc/staking/unstake" in path:
                raise _network_error(410, {"detail": RETIRED_DETAIL})
            return {}

        mock_rpc.client.post.side_effect = post
        result = runner.invoke(
            wallet,
            ["--wallet-path", temp_wallet, "unstake", "--stake-id", "7"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "Retired RPC surface" in result.output
        assert "Staking is retired" in result.output

    def test_wallet_unstake_non_410_keeps_legacy_error(self, runner, temp_wallet, mock_rpc):
        def post(path, json=None):
            if "/rpc/staking/unstake" in path:
                raise _network_error(409, {"detail": "lock conflict"})
            return {}

        mock_rpc.client.post.side_effect = post
        result = runner.invoke(
            wallet,
            ["--wallet-path", temp_wallet, "unstake", "--stake-id", "7"],
            obj={"output_format": "json"},
        )
        assert result.exit_code != 0
        assert "Error unstaking tokens:" in result.output
        assert "lock conflict" in result.output
        assert "Retired RPC surface" not in result.output
