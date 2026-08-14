"""Tests for AI router module"""

from agent_app.routers.ai import router


class TestAIRouter:
    """Test AI router endpoints"""

    def test_router_initialization(self):
        """Test router is initialized correctly"""
        assert router is not None
        assert len(router.routes) > 0
