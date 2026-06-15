"""Tests for AI router module"""

from unittest.mock import AsyncMock, Mock

import pytest
from app.routers.ai import router


class TestAIRouter:
    """Test AI router endpoints"""

    @pytest.mark.asyncio
    async def test_record_learning_experience_success(self):
        """Test successful learning experience recording"""
        from app.ai.realtime_learning import learning_system

        learning_system.record_experience = AsyncMock(return_value={"status": "success", "experience_id": "exp-1"})

        request = Mock()
        experience_data = {"context": {"env": "prod"}, "action": "test", "outcome": "success", "reward": 1.0}

        # Find the endpoint function
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/ai/learning/experience":
                result = await route.endpoint(request, experience_data)
                assert result["status"] == "success"
                assert result["experience_id"] == "exp-1"
                break

    @pytest.mark.asyncio
    async def test_record_learning_experience_error(self):
        """Test learning experience recording with error"""
        from app.ai.realtime_learning import learning_system

        learning_system.record_experience = AsyncMock(side_effect=Exception("Test error"))

        request = Mock()
        experience_data = {"context": {}, "action": "test"}

        # Find the endpoint function
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/ai/learning/experience":
                with pytest.raises(Exception):  # noqa: B017
                    await route.endpoint(request, experience_data)
                break

    @pytest.mark.asyncio
    async def test_get_learning_statistics_success(self):
        """Test successful learning statistics retrieval"""
        from app.ai.realtime_learning import learning_system

        learning_system.get_learning_statistics = AsyncMock(return_value={"total_experiences": 100, "avg_reward": 0.95})

        request = Mock()

        # Find the endpoint function
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/ai/learning/statistics":
                result = await route.endpoint(request)
                assert result["total_experiences"] == 100
                assert result["avg_reward"] == 0.95
                break

    @pytest.mark.asyncio
    async def test_predict_performance_success(self):
        """Test successful performance prediction"""
        from app.ai.realtime_learning import learning_system

        learning_system.predict_performance = AsyncMock(return_value={"predicted_performance": 0.92})

        request = Mock()
        context = {"env": "prod"}
        action = "process_data"

        # Find the endpoint function
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/ai/learning/predict":
                result = await route.endpoint(request, context, action)
                assert result["predicted_performance"] == 0.92
                break

    @pytest.mark.asyncio
    async def test_recommend_action_success(self):
        """Test successful action recommendation"""
        from app.ai.realtime_learning import learning_system

        learning_system.recommend_action = AsyncMock(return_value={"recommended_action": "process_data", "confidence": 0.95})

        request = Mock()
        context = {"env": "prod"}
        available_actions = ["process_data", "analyze_data"]

        # Find the endpoint function
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/ai/learning/recommend":
                result = await route.endpoint(request, context, available_actions)
                assert result["recommended_action"] == "process_data"
                assert result["confidence"] == 0.95
                break

    def test_router_initialization(self):
        """Test router is initialized correctly"""
        assert router is not None
        assert len(router.routes) > 0
