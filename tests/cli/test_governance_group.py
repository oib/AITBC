"""Tests for the aitbc governance command group (P1.7 lifecycle)."""

from unittest.mock import patch

import pytest


@pytest.fixture
def gov_ctx_obj():
    return {
        "output": "json",
        "output_format": "json",
        "url": None,
        "api_key": None,
        "verbose": 0,
        "debug": False,
    }


class TestGovernanceClose:
    @patch("aitbc_cli.commands.governance.AITBCHTTPClient")
    def test_close_proposal(self, mock_client_class, runner, gov_ctx_obj):
        mock_client = mock_client_class.return_value
        mock_client.post.return_value = {
            "proposal_id": "prop-123",
            "status": "succeeded",
            "yes_votes": 10.0,
            "no_votes": 2.0,
        }

        from aitbc_cli.commands.governance import governance

        result = runner.invoke(governance, ["close", "--proposal-id", "prop-123"], obj=gov_ctx_obj)

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/v1/governance/proposals/prop-123/close" in mock_client.post.call_args[0][0]


class TestGovernanceProposalShow:
    """`governance proposal show` reads the sealed PROPOSE via the node's own
    blockchain RPC (canonical transaction table), not the governance service
    (GAP-PROPOSAL-SHOW-1)."""

    @patch("aitbc_cli.commands.governance._governance_rpc")
    def test_show_calls_chain_rpc(self, mock_rpc, runner, gov_ctx_obj):
        mock_client = mock_rpc.return_value[0]
        mock_client.get.return_value = {
            "proposal_id": "prop-17",
            "tx_hash": "0xabc",
            "block_height": 42,
            "execution_payload": {"parameter": "p", "value": "v"},
            "executed": False,
        }
        mock_rpc.return_value = (mock_client, "ait-testchain.local")

        from aitbc_cli.commands.governance import governance

        result = runner.invoke(
            governance, ["proposal", "show", "--proposal-id", "prop-17"], obj=gov_ctx_obj
        )

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once_with(
            "/rpc/governance/sealed-proposal/prop-17", params={"chain_id": "ait-testchain.local"}
        )
        assert "execution_payload" in result.output
