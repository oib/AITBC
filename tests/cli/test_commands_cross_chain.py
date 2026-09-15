"""
Cross Chain Commands Tests
Tests for cross_chain CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestCrossChainCommands:
    """Test cross_chain command group"""

    def test_cross_chain_group_exists(self):
        """Test that cross_chain command group exists"""
        from aitbc_cli.commands.cross_chain import cross_chain

        assert cross_chain is not None
        assert hasattr(cross_chain, "name")

    def test_cross_chain_group_name(self):
        """Test cross_chain group name"""
        from aitbc_cli.commands.cross_chain import cross_chain

        assert cross_chain.name == "cross-chain"

    def test_cross_chain_group_has_rates_subcommand(self):
        """The ``rates`` subcommand is registered on the cross_chain group."""
        from aitbc_cli.commands.cross_chain import cross_chain

        assert "rates" in cross_chain.commands

    def test_cross_chain_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the cross_chain group."""
        from aitbc_cli.commands.cross_chain import cross_chain

        assert "status" in cross_chain.commands

    @patch("aitbc_cli.commands.cross_chain.AITBCHTTPClient")
    def test_cross_chain_rates_command(self, mock_http_class, runner, mock_config):
        """``cross-chain rates`` returns exchange rates from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"rates": {"chain-a-chain-b": 1.5}}

        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            ["rates"],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()

    @patch("aitbc_cli.commands.cross_chain.AITBCHTTPClient")
    def test_cross_chain_rates_command_specific_pair(self, mock_http_class, runner, mock_config):
        """``cross-chain rates --from-chain --to-chain`` filters to a specific pair."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"rates": {"chain-a-chain-b": 1.5}}

        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            ["rates", "--from-chain", "chain-a", "--to-chain", "chain-b"],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.commands.cross_chain.AITBCHTTPClient")
    def test_cross_chain_status_command(self, mock_http_class, runner, mock_config):
        """``cross-chain status`` returns swap status from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {
            "swap_id": "swap123",
            "status": "completed",
            "from_chain": "chain-a",
            "to_chain": "chain-b",
        }

        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            ["status", "--swap-id", "swap123"],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        called_path = mock_client.get.call_args[0][0]
        assert called_path == "/rpc/cross-chain/swap/swap123"


class TestCrossChainSigning:
    """GAP-47: swap/bridge must POST wallet-signed payloads to the real RPC.

    The autouse ``_mock_payment_wallet`` conftest fixture returns a real
    ephemeral secp256k1 keypair, so the posted ``signature`` is a genuine
    recoverable signature over the canonical request payload — the same
    convention ``transactions send`` and ``/rpc/bridge/lock`` use.
    """

    @staticmethod
    def _recover(signature: str, sign_data: dict) -> str:
        import json

        from eth_keys import keys
        from eth_utils import keccak

        message = json.dumps(sign_data, sort_keys=True, separators=(",", ":")).encode()
        sig = keys.Signature(signature_bytes=bytes.fromhex(signature.removeprefix("0x")))
        return str(sig.recover_public_key_from_msg_hash(keccak(message)).to_checksum_address())

    @patch("aitbc_cli.commands.cross_chain.AITBCHTTPClient")
    def test_swap_posts_signed_payload_to_rpc(self, mock_http_class, runner, mock_config):
        """``crosschain swap`` signs the swap request and POSTs it to /rpc/swap."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {
            "success": True,
            "swap_id": "swap_abc",
            "transfer_id": "0xrealtxhash",
            "status": "pending",
            "from_tx_hash": "0xrealtxhash",
        }

        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            [
                "swap",
                "--from-chain",
                "chain-a",
                "--to-chain",
                "chain-b",
                "--from-token",
                "AIT",
                "--to-token",
                "AIT",
                "--amount",
                "1",
            ],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        called_path, called_kwargs = mock_client.post.call_args[0][0], mock_client.post.call_args[1]
        assert called_path == "/rpc/swap"
        posted = called_kwargs["json"]
        assert posted["signature"].startswith("0x")
        assert posted["from_chain"] == "chain-a"
        assert posted["to_chain"] == "chain-b"
        # The signature must recover the sender over the signed fields.
        sign_data = {k: v for k, v in posted.items() if k != "signature"}
        recovered = self._recover(posted["signature"], sign_data)
        assert recovered.lower() == posted["sender"].lower()

    @patch("aitbc_cli.commands.cross_chain.AITBCHTTPClient")
    def test_bridge_posts_signed_lock_payload(self, mock_http_class, runner, mock_config):
        """``crosschain bridge`` signs the six-field lock payload like /rpc/bridge/lock."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {
            "success": True,
            "bridge_id": "0xrealtxhash",
            "source_tx_hash": "0xrealtxhash",
            "status": "pending",
        }

        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            [
                "bridge",
                "--source-chain",
                "chain-a",
                "--target-chain",
                "chain-b",
                "--token",
                "AIT",
                "--amount",
                "1",
            ],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output
        called_path, called_kwargs = mock_client.post.call_args[0][0], mock_client.post.call_args[1]
        assert called_path == "/rpc/cross-chain/bridge"
        posted = called_kwargs["json"]
        assert posted["signature"].startswith("0x")
        # The bridge lock payload is exactly the six fields the RPC verifies.
        sign_data = {k: posted[k] for k in ("source_chain", "target_chain", "sender", "recipient", "amount", "asset")}
        recovered = self._recover(posted["signature"], sign_data)
        assert recovered.lower() == posted["sender"].lower()

    @patch("aitbc_cli.commands.cross_chain.AITBCHTTPClient")
    def test_swap_reports_real_tx_hash(self, mock_http_class, runner, mock_config):
        """The command surfaces the real source tx hash, not a synthetic one."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {
            "success": True,
            "swap_id": "swap_abc",
            "transfer_id": "0xdeadbeef" + "00" * 28,
            "status": "pending",
            "from_tx_hash": "0xdeadbeef" + "00" * 28,
        }

        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            [
                "swap",
                "--from-chain",
                "chain-a",
                "--to-chain",
                "chain-b",
                "--from-token",
                "AIT",
                "--to-token",
                "AIT",
                "--amount",
                "1",
            ],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output
        assert "0xdeadbeef" in result.output

    def test_swap_rejects_same_chain(self, runner, mock_config):
        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            [
                "swap",
                "--from-chain",
                "chain-a",
                "--to-chain",
                "chain-a",
                "--from-token",
                "AIT",
                "--to-token",
                "AIT",
                "--amount",
                "1",
            ],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code != 0
        assert "different" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
