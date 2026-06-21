"""
AI Handlers Tests
Tests for ai CLI handlers
"""

import pytest


# The handlers package was removed during CLI consolidation; skip all
# tests in this module rather than failing on the @patch decorator.
pytestmark = pytest.mark.skip(reason="handlers package no longer exists (consolidated into aitbc_cli.commands)")


class TestAIHandlers:
    """Test AI handlers"""

    def test_handle_ai_submit_function_exists(self):
        """Test that handle_ai_submit function exists"""
        from handlers.ai import handle_ai_submit

        assert handle_ai_submit is not None

    def test_handle_ai_submit_command(self):
        """Test handle_ai_submit - skip due to complex keystore and RPC dependencies"""
        from handlers.ai import handle_ai_submit

        assert handle_ai_submit is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
