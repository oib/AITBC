"""Tests for coordinator-api utility functions"""

import sys

sys.path.insert(0, "/opt/aitbc/apps/coordinator-api/src")

from unittest.mock import MagicMock, patch

import pytest

from app.routers.users import create_session_token, verify_session_token


class TestUserSessionTokens:
    def test_create_session_token(self):
        token = create_session_token("user1")
        assert token is not None
        assert len(token) == 64

    def test_verify_session_token_valid(self):
        token = create_session_token("user1")
        user_id = verify_session_token(token)
        assert user_id == "user1"

    def test_verify_session_token_invalid(self):
        user_id = verify_session_token("invalid_token")
        assert user_id is None


class TestRegistry:
    def test_create_service_registry(self):
        from app.routers.registry import create_service_registry

        registry = create_service_registry()
        assert registry is not None


class TestMetrics:
    def test_get_metrics(self):
        from app.utils.metrics import get_metrics

        metrics = get_metrics()
        assert isinstance(metrics, dict)

    def test_reset_metrics(self):
        from app.utils.metrics import reset_metrics

        reset_metrics()
