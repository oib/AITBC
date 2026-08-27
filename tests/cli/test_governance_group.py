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

        result = runner.invoke(governance, ["close", "prop-123"], obj=gov_ctx_obj)

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/v1/governance/proposals/prop-123/close" in mock_client.post.call_args[0][0]
