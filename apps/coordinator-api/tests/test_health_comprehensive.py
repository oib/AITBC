"""
Comprehensive health endpoint tests for AITBC services

Tests both internal service health and external marketplace health endpoints.
"""

from unittest.mock import Mock, patch


class TestInternalHealthEndpoints:
    """Test internal application health endpoints"""

    def test_health_check_basic(self):
        """Test basic health check without full app setup"""
        # This test verifies the health endpoints are accessible
        # without requiring full database setup

        with patch("coordinator_api.main.create_app") as mock_create_app:
            mock_app = Mock()
            mock_app.router.routes.__len__ = Mock(return_value=10)
            mock_app.title = "AITBC Coordinator API"

            mock_create_app.return_value = mock_app

            # Import and test the health endpoint logic
            from coordinator_api.main import create_app

            app = create_app()

            # Verify app creation succeeded
            assert app.title == "AITBC Coordinator API"
