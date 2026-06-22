"""
Account Handlers Tests
Tests for account CLI handlers
"""

import pytest


# The handlers package was removed during CLI consolidation; skip all
# tests in this module rather than failing on the @patch decorator.
pytestmark = pytest.mark.skip(reason="handlers package no longer exists (consolidated into aitbc_cli.commands)")


class TestAccountHandlers:
    """Test account handlers"""

    def test_render_mapping_function_exists(self):
        """Test that render_mapping function exists"""
        from handlers.account import render_mapping

        assert render_mapping is not None

    def test_handle_account_get_function_exists(self):
        """Test that handle_account_get function exists"""
        from handlers.account import handle_account_get

        assert handle_account_get is not None

    def test_handle_account_get_command(self):
        """Test handle_account_get - skip due to complex RPC dependencies"""
        from handlers.account import handle_account_get

        assert handle_account_get is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
