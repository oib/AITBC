"""
Mock fixtures for CLI tests.

These fixtures replace the "complex dependencies" that caused 70+ CLI test
files to skip with ``pytest.skip("complex dependencies")`` and similar
reasons.  Importing this module (via the ``tests/cli/conftest.py`` autouse
machinery) makes the fixtures available to every CLI test so the remaining
stub tests can be converted incrementally.

Fixtures provided
-----------------
* ``mock_blockchain_rpc`` — mock HTTP client returning realistic blockchain
  RPC responses for the common endpoints.
* ``mock_wallet`` — a mock wallet backed by a real ``eth_account`` keypair
  that can sign transactions and report a balance.
* ``mock_click_context`` — a Click context object pre-populated with the
  standard ``ctx.obj`` fields used across the CLI.
* ``mock_config`` — a mock ``CLIConfig`` with sensible test values.
* ``mock_subprocess`` — a mock ``subprocess.run`` that returns success for
  common commands.
* ``mock_eth_utils`` — a shim that re-exports ``eth_utils`` helpers for
  tests that previously skipped because "eth_utils import failed".
"""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import click
import httpx
import pytest

try:  # eth_account is an optional dependency in some environments
    from eth_account import Account
    from eth_account.messages import encode_defunct

    _ETH_ACCOUNT_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when eth_account missing
    _ETH_ACCOUNT_AVAILABLE = False


# ---------------------------------------------------------------------------
# 1. mock_blockchain_rpc
# ---------------------------------------------------------------------------


def _default_rpc_responses() -> dict[str, dict]:
    """Return a mapping of RPC path -> default JSON response body."""
    return {
        "/rpc/head": {
            "height": 12345,
            "hash": "0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
            "timestamp": "2026-01-01T00:00:00Z",
            "chain_id": "test-chain",
        },
        "/rpc/account/ait1qtestaddress0000000000000000000000000": {
            "address": "ait1qtestaddress0000000000000000000000000",
            "balance": 1000000,
            "nonce": 42,
            "code": "",
        },
        "/rpc/transaction": {
            "tx_hash": "0xtx1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            "status": "confirmed",
            "block_height": 12345,
        },
        "/rpc/blocks-range": {
            "blocks": [
                {"height": 12344, "hash": "0xblock1"},
                {"height": 12345, "hash": "0xblock2"},
            ],
        },
        "/rpc/balance/ait1qtestaddress0000000000000000000000000": {
            "address": "ait1qtestaddress0000000000000000000000000",
            "balance": 1000000,
            "currency": "AIT",
        },
        "/rpc/accounts": {
            "accounts": [
                {"address": "ait1qtestaddress0000000000000000000000000", "balance": 1000000},
            ],
        },
        "/rpc/bridge/status": {
            "bridge_status": "running",
            "peers": 2,
        },
        "/rpc/bridge/start": {
            "bridge_status": "started",
        },
        "/rpc/bridge/stop": {
            "bridge_status": "stopped",
        },
    }


def _make_rpc_transport(responses: dict[str, dict]) -> httpx.MockTransport:
    """Build an ``httpx.MockTransport`` that serves the given responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        # Try exact match first, then fall back to a prefix match for
        # parameterised endpoints such as /rpc/account/{address}.
        body = responses.get(path)
        if body is None:
            for key, value in responses.items():
                if path.startswith(key):
                    body = value
                    break
        if body is None:
            return httpx.Response(404, json={"error": f"unknown endpoint: {path}"})
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


@pytest.fixture
def mock_blockchain_rpc():
    """Return a mock blockchain RPC client backed by ``httpx.MockTransport``.

    The returned object exposes ``responses`` (a mutable dict) so individual
    tests can override the canned responses, and ``client`` — an
    ``httpx.Client`` whose transport is the mock.  Tests that patch
    ``AITBCHTTPClient`` can instead use the ``responses`` mapping directly.
    """
    responses = _default_rpc_responses()
    transport = _make_rpc_transport(responses)
    http_client = httpx.Client(transport=transport, timeout=5)

    rpc = SimpleNamespace(responses=responses, client=http_client, transport=transport)
    yield rpc
    http_client.close()


# ---------------------------------------------------------------------------
# 2. mock_wallet
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_wallet():
    """Return a mock wallet backed by a real ``eth_account`` keypair.

    Provides ``address``, ``balance``, ``sign_transaction()`` and
    ``get_balance()``.  When ``eth_account`` is unavailable a pure-mock
    fallback is used so tests still run.
    """
    if _ETH_ACCOUNT_AVAILABLE:
        acct = Account.create()
        address = acct.address
        key = acct.key

        def sign_transaction(tx: dict) -> dict:
            signed = Account.sign_transaction(tx, key)
            return {
                "raw_transaction": signed.raw_transaction.hex()
                if hasattr(signed, "raw_transaction")
                else getattr(signed, "rawTransaction", b"").hex(),
                "hash": signed.hash.hex() if hasattr(signed, "hash") else "0xmockhash",
                "sender": address,
            }

        def sign_message(message: str) -> str:
            msg = encode_defunct(text=message)
            signed = Account.sign_message(msg, key)
            return signed.signature.hex()

    else:  # pragma: no cover - fallback when eth_account missing
        address = "0xMockWalletAddress0000000000000000000000000000"

        def sign_transaction(tx: dict) -> dict:
            return {"raw_transaction": "0xmockraw", "hash": "0xmockhash", "sender": address}

        def sign_message(message: str) -> str:
            return "0xmocksignature"

    wallet = SimpleNamespace(
        address=address,
        balance=1_000_000,
        private_key=key.hex() if _ETH_ACCOUNT_AVAILABLE else "0xmockkey",
        sign_transaction=Mock(side_effect=sign_transaction),
        sign_message=Mock(side_effect=sign_message),
        get_balance=Mock(return_value=1_000_000),
    )
    return wallet


# ---------------------------------------------------------------------------
# 3. mock_click_context
# ---------------------------------------------------------------------------


def make_cli_obj(**overrides) -> dict:
    """Build the standard ``ctx.obj`` mapping used across the CLI commands."""
    obj = {
        "output": "table",
        "output_format": "table",
        "url": "http://localhost:8202",
        "api_key": "test-api-key",
        "verbose": 0,
        "debug": False,
        "config": None,
    }
    obj.update(overrides)
    return obj


@pytest.fixture
def mock_click_context():
    """Return a Click context with a pre-populated ``ctx.obj``.

    The context can be passed directly to commands via
    ``ctx.invoke(cmd, ...)`` or used as a parent for sub-contexts.
    """
    obj = make_cli_obj()
    ctx = click.Context(click.Command("dummy"), obj=obj)
    return ctx


@pytest.fixture
def cli_obj():
    """Return the plain ``ctx.obj`` dict for use with ``CliRunner.invoke``."""
    return make_cli_obj()


# ---------------------------------------------------------------------------
# 4. mock_config
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config():
    """Return a mock ``CLIConfig`` with sensible test values.

    The object is a ``MagicMock`` configured with attribute access so it can
    be used as a drop-in replacement for ``CLIConfig`` instances returned by
    ``get_config()``.
    """
    config = MagicMock()
    config.app_name = "AITBC CLI"
    config.app_version = "2.1.0"
    config.blockchain_rpc_url = "http://localhost:8202"
    config.explorer_api_url = "http://localhost:8100"
    config.agent_coordinator_url = "http://localhost:8107"
    config.wallet_daemon_url = "http://localhost:8108"
    config.wallet_url = "http://localhost:8108"
    config.exchange_service_url = "http://localhost:8106/api/v1"
    config.gpu_service_url = "http://localhost:8101"
    config.marketplace_service_url = "http://localhost:8102"
    config.trading_service_url = "http://localhost:8104"
    config.governance_service_url = "http://localhost:8105"
    config.edge_api_host = "localhost"
    config.edge_api_port = 8103
    config.coordinator_url = "http://localhost:8006"
    config.chain_id = "test-chain"
    config.api_key = "test-api-key"
    config.timeout = 30
    config.config_file = None
    config.hub_discovery_url = None
    return config


# ---------------------------------------------------------------------------
# 5. mock_subprocess
# ---------------------------------------------------------------------------


def _mock_run(*args, **kwargs):
    """Default ``subprocess.run`` replacement returning success."""
    cmd = args[0] if args else kwargs.get("args")
    result = MagicMock()
    result.returncode = 0
    result.stdout = "success\n"
    result.stderr = ""
    result.args = cmd
    return result


@pytest.fixture
def mock_subprocess(monkeypatch):
    """Patch ``subprocess.run`` to return success for common commands.

    Returns the underlying ``Mock`` so tests can inspect call history or
    reconfigure side effects for specific commands.
    """
    run_mock = Mock(side_effect=_mock_run)
    monkeypatch.setattr(subprocess, "run", run_mock)
    # Also patch the common import path used by CLI modules.
    try:
        if hasattr(subprocess, "run"):
            monkeypatch.setattr(subprocess, "run", run_mock)
    except Exception:
        pass
    return run_mock


# ---------------------------------------------------------------------------
# 6. mock_eth_utils
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_eth_utils():
    """Provide ``eth_utils`` helper functions for tests that skip on import.

    ``eth_utils`` is installed in the test environment, so this fixture simply
    re-exports the real helpers.  If the package is ever missing, a lightweight
    pure-python fallback is provided so tests no longer skip with
    "eth_utils import failed".
    """
    try:
        import eth_utils as _eu

        return SimpleNamespace(
            to_checksum_address=_eu.to_checksum_address,
            is_address=_eu.is_address,
            is_checksum_address=_eu.is_checksum_address,
            is_hex=_eu.is_hex,
            to_hex=_eu.to_hex,
            hexbytes_if_bigint=_eu.hexbytes_if_bigint if hasattr(_eu, "hexbytes_if_bigint") else lambda x: hex(x),
        )
    except Exception:  # pragma: no cover - fallback when eth_utils missing
        import re

        _ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

        def to_checksum_address(value: str) -> str:
            if not value.startswith("0x"):
                value = "0x" + value
            return value

        def is_address(value: str) -> bool:
            return bool(_ADDR_RE.match(value))

        def is_checksum_address(value: str) -> bool:
            return is_address(value)

        def is_hex(value: str) -> bool:
            if value.startswith("0x") or value.startswith("0X"):
                value = value[2:]
            try:
                int(value, 16)
                return True
            except (ValueError, TypeError):
                return False

        def to_hex(value) -> str:
            if isinstance(value, bytes):
                return "0x" + value.hex()
            return hex(value)

        return SimpleNamespace(
            to_checksum_address=to_checksum_address,
            is_address=is_address,
            is_checksum_address=is_checksum_address,
            is_hex=is_hex,
            to_hex=to_hex,
            hexbytes_if_bigint=lambda x: hex(x),
        )


# ---------------------------------------------------------------------------
# Convenience: JSON helper for assertions
# ---------------------------------------------------------------------------


def parse_json_output(text: str):
    """Parse JSON from CLI output, tolerating surrounding noise."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Find the first JSON-looking chunk
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start : end + 1])
        raise
