"""
Contract Commands Tests
Tests for contract CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _rpc_api_key_env(monkeypatch, tmp_path):
    """#2350: contract POSTs require the RPC key — default the env so the
    pre-existing command tests exercise the keyed path. Point config
    resolution at a nonexistent file so a real ~/.aitbc.yaml can't leak in."""
    monkeypatch.setenv("BLOCKCHAIN_RPC_API_KEY", "env-test-key")
    monkeypatch.setenv("AITBC_CONFIG_FILE", str(tmp_path / "no-such-config.yaml"))


class TestContractCommands:
    """Test contract command group"""

    def test_contract_group_exists(self):
        """Test that contract command group exists"""
        from aitbc_cli.commands.contract import contract

        assert contract is not None
        assert hasattr(contract, "name")

    def test_contract_group_name(self):
        """Test contract group name"""
        from aitbc_cli.commands.contract import contract

        assert contract.name == "contract"

    def test_contract_group_has_deploy_subcommand(self):
        """The ``deploy`` subcommand is registered on the contract group."""
        from aitbc_cli.commands.contract import contract

        assert "deploy" in contract.commands

    def test_contract_group_has_call_subcommand(self):
        """The ``call`` subcommand is registered on the contract group."""
        from aitbc_cli.commands.contract import contract

        assert "call" in contract.commands

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_contract_deploy_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``contract deploy`` deploys a contract via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"tx_hash": "0xdeploy123", "status": "confirmed"}

        from aitbc_cli.commands.contract import contract

        result = runner.invoke(
            contract,
            ["deploy", "--contract-name", "MyContract"],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        # The deploy handler reads ``name``/``type``/``deployer`` — sending
        # ``contract_name`` was silently rejected as "name is required".
        called_path, called_kwargs = mock_client.post.call_args[0][0], mock_client.post.call_args[1]
        assert "/rpc/contracts/deploy" in called_path
        assert called_kwargs["json"] == {"name": "MyContract"}

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_contract_call_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``contract call`` calls a contract method via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"result": "0xreturnvalue", "status": "success"}

        from aitbc_cli.commands.contract import contract

        result = runner.invoke(
            contract,
            [
                "call",
                "--contract-address",
                "0xA1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4",
                "--method",
                "balanceOf",
                "--args",
                '["0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"]',
            ],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        called_path = mock_client.post.call_args[0][0]
        called_json = mock_client.post.call_args[1]["json"]
        assert "/rpc/contracts/call" in called_path
        # The call handler reads ``address``/``method``/``params`` —
        # ``contract_address``/``args`` were rejected as missing fields.
        assert called_json["address"] == "0xA1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4"
        assert called_json["method"] == "balanceOf"
        assert called_json["params"] == ["0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"]
        assert "contract_address" not in called_json
        assert "args" not in called_json

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_contract_call_command_no_args(self, mock_http_class, runner, mock_blockchain_rpc):
        """``contract call`` without ``--args`` sends no ``params`` key."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"result": "0x", "status": "success"}

        from aitbc_cli.commands.contract import contract

        result = runner.invoke(
            contract,
            [
                "call",
                "--contract-address",
                "0xA1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4",
                "--method",
                "totalSupply",
            ],
        )

        assert result.exit_code == 0, result.output
        called_json = mock_client.post.call_args[1]["json"]
        assert called_json == {
            "address": "0xA1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4",
            "method": "totalSupply",
        }

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_contract_deploy_network_error_aborts(self, mock_http_class, runner):
        """``contract deploy`` aborts (non-zero) on a NetworkError."""
        from aitbc_cli.commands.contract import contract
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(
            contract,
            ["deploy", "--contract-name", "MyContract"],
        )

        assert result.exit_code != 0

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_deploy_sends_env_api_key(self, mock_http_class, runner):
        """#2350: the env/config key reaches the client as ``api_key`` (X-API-Key)."""
        mock_http_class.return_value.post.return_value = {"status": "confirmed"}

        from aitbc_cli.commands.contract import contract

        result = runner.invoke(contract, ["deploy", "--contract-name", "MyContract"])

        assert result.exit_code == 0, result.output
        assert mock_http_class.call_args.kwargs.get("api_key") == "env-test-key"

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_deploy_api_key_flag_wins_over_env(self, mock_http_class, runner):
        mock_http_class.return_value.post.return_value = {"status": "confirmed"}

        from aitbc_cli.commands.contract import contract

        result = runner.invoke(
            contract, ["deploy", "--contract-name", "MyContract", "--api-key", "flag-key"]
        )

        assert result.exit_code == 0, result.output
        assert mock_http_class.call_args.kwargs.get("api_key") == "flag-key"

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_call_and_verify_send_api_key(self, mock_http_class, runner):
        mock_http_class.return_value.post.return_value = {"result": "0x", "status": "success"}

        from aitbc_cli.commands.contract import contract

        r1 = runner.invoke(
            contract,
            ["call", "--contract-address", "0x" + "ab" * 20, "--method", "totalSupply"],
        )
        assert r1.exit_code == 0, r1.output
        assert mock_http_class.call_args.kwargs.get("api_key") == "env-test-key"

        r2 = runner.invoke(
            contract,
            ["verify", "--contract-address", "0x" + "ab" * 20, "--proof", '{"pi_a": 1}'],
        )
        assert r2.exit_code == 0, r2.output
        assert mock_http_class.call_args.kwargs.get("api_key") == "env-test-key"

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_missing_api_key_fails_with_guidance(self, mock_http_class, runner, monkeypatch):
        """#2350: no flag/env/config key -> UsageError naming both sources,
        not a bare server 403."""
        monkeypatch.delenv("BLOCKCHAIN_RPC_API_KEY", raising=False)

        from aitbc_cli.commands.contract import contract

        result = runner.invoke(contract, ["deploy", "--contract-name", "MyContract"])

        assert result.exit_code != 0
        assert "--api-key" in result.output
        assert "BLOCKCHAIN_RPC_API_KEY" in result.output
        mock_http_class.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
