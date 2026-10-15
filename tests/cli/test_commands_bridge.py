"""
Bridge Commands Tests
Tests for bridge CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

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
