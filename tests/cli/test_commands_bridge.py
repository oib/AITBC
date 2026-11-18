"""
Bridge Commands Tests
Tests for bridge CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import httpx
import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestBridgeCommands:
    """Test bridge command group"""

    def test_bridge_group_exists(self):
        """Test that bridge command group exists"""
        from aitbc_cli.commands.bridge import bridge

        assert bridge is not None
        assert hasattr(bridge, "name")

    def test_bridge_group_name(self):
        """Test bridge group name"""
        from aitbc_cli.commands.bridge import bridge

        assert bridge.name == "bridge"

    def test_bridge_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the bridge group."""
        from aitbc_cli.commands.bridge import bridge

        assert "status" in bridge.commands


class TestBridgeErrorDetail:
    """#2214: bridge RPC failures must surface the server's JSON error detail."""

    @staticmethod
    def _http_error(status: int, body: dict) -> httpx.HTTPStatusError:
        request = httpx.Request("POST", "http://node:8202/rpc/bridge/lock")
        response = httpx.Response(status, json=body, request=request)
        return httpx.HTTPStatusError(f"Client error '{status}' for url", request=request, response=response)

    def test_detail_string_extracted(self):
        from aitbc_cli.commands.bridge._helpers import _response_error_detail

        err = self._http_error(422, {"detail": "amount must be greater than 0"})
        assert _response_error_detail(err) == "amount must be greater than 0"

    def test_detail_fastapi_list_extracted(self):
        from aitbc_cli.commands.bridge._helpers import _response_error_detail

        err = self._http_error(422, {"detail": [{"loc": ["body", "amount"], "msg": "value is not a valid integer"}]})
        assert _response_error_detail(err) == "value is not a valid integer"

    def test_no_response_returns_none(self):
        from aitbc_cli.commands.bridge._helpers import _response_error_detail

        assert _response_error_detail(RuntimeError("boom")) is None

    def test_pending_command_surfaces_server_detail(self, runner):
        from aitbc_cli.commands.bridge import bridge

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def list_pending(self, chain_id=None):
                raise self._err

        fake = _FakeClient()
        fake._err = self._http_error(422, {"detail": "chain_id filter is not a valid chain"})
        with patch("aitbc_cli.commands.bridge._get_bridge_client", return_value=fake):
            result = runner.invoke(bridge, ["pending"])

        assert result.exit_code != 0
        assert "chain_id filter is not a valid chain" in result.output
        assert "Client error '422'" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestSellLockChainId:
    """sell lock is a signing path: no explicit chain id + unreachable probe
    must abort with the chain-id message and sign nothing (WAL-1 fix)."""

    def test_sell_lock_aborts_when_chain_id_unresolvable(self, runner, tmp_path, monkeypatch):
        from aitbc_cli.commands.wallet import bridge as bridge_mod

        monkeypatch.delenv("CHAIN_ID", raising=False)
        monkeypatch.delenv("AITBC_WALLET_PASSWORD", raising=False)

        wallet_file = tmp_path / "w.json"
        wallet_file.write_text('{"address": "0xFCAd0B19bB29D4674531d6f115237E16AfCE377c", "private_key": "' + "ab" * 32 + '"}')
        monkeypatch.setattr(
            bridge_mod,
            "_resolve_wallet",
            lambda ctx, name, **kw: {
                "address": "0xFCAd0B19bB29D4674531d6f115237E16AfCE377c",
                "private_key": "ab" * 32,
            },
        )

        class _HubClient:
            def get(self, path, **kw):
                return {
                    "kind": "quote",
                    "status": "quoted",
                    "escrow_address": "0x" + "11" * 20,
                    "ait_amount": "1",
                }

        monkeypatch.setattr(bridge_mod, "_hub_bridge_client", lambda url: _HubClient())

        class _Cfg:
            blockchain_rpc_url = "http://127.0.0.1:1"

        monkeypatch.setattr(bridge_mod, "get_config", lambda: _Cfg())

        posts: list = []
        monkeypatch.setattr(
            bridge_mod.AITBCHTTPClient,
            "post",
            lambda self, *a, **kw: posts.append((a, kw)) or {},
        )

        result = runner.invoke(
            bridge_mod.sell_lock,
            ["--quote-id", "sellq_test", "--wallet-name", "w"],
            obj={},
        )
        assert result.exit_code != 0
        assert "Chain ID lookup" in result.output or "chain" in result.output.lower()
        assert not posts, "no transaction may be submitted when the chain id cannot be resolved"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
