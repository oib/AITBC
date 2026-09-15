"""
Bond Commands Tests
Tests for bond CLI commands

Follows the shared CLI mock fixtures convention (see
``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestBondCommands:
    """Test bond command group"""

    def test_bond_group_exists(self):
        """Test that bond command group exists"""
        from aitbc_cli.commands.bond import bond

        assert bond is not None
        assert hasattr(bond, "name")

    def test_bond_group_name(self):
        """Test bond group name"""
        from aitbc_cli.commands.bond import bond

        assert bond.name == "bond"

    def test_bond_group_has_release_subcommand(self):
        """The ``release`` subcommand is registered on the bond group."""
        from aitbc_cli.commands.bond import bond

        assert "release" in bond.commands

    @patch("aitbc_cli.commands.bond._api_client")
    def test_bond_release_explains_active_status(self, mock_api_client, runner, cli_obj):
        """``bond release`` annotates the 'active' status the coordinator returns.

        The service intentionally returns the bond to ``active`` on release —
        release un-locks a locked bond, it does not withdraw the funds — so the
        CLI output must explain that ``active`` is the released state.
        """
        mock_client = MagicMock()
        mock_client.post.return_value = {
            "id": "pb_1",
            "provider_id": "provider-1",
            "bond_id": "bond-1",
            "status": "active",
            "amount": "1.0",
            "required_amount": "1.0",
            "meta": {},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-02T00:00:00",
        }
        mock_api_client.return_value = mock_client

        from aitbc_cli.commands.bond import bond

        result = runner.invoke(bond, ["release", "--provider-id", "provider-1"], obj=cli_obj)

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once_with("/v1/marketplace/providers/provider-1/bonds/release")
        # The accurate status is still shown, with an explicit explanation.
        assert '"status": "active"' in result.output
        assert "does not withdraw" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
