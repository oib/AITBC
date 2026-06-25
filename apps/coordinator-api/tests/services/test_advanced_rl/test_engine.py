"""
Tests for advanced RL engine
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestAdvancedReinforcementLearningEngine:
    """Test Advanced Reinforcement Learning Engine"""

    def test_engine_initialization(self):
        """Test engine initialization"""
        from app.contexts.advanced_rl.services.advanced_rl.engine import AdvancedReinforcementLearningEngine

        engine = AdvancedReinforcementLearningEngine()

        assert engine.device is not None
        assert engine.agents == {}
        assert engine.training_histories == {}
        assert len(engine.rl_algorithms) > 0

    @pytest.mark.skip(reason="torch operations too slow for CI")
    @patch("app.contexts.advanced_rl.services.advanced_rl.engine.Session")
    async def test_proximal_policy_optimization(self, mock_session):
        """Test PPO training"""
        from app.contexts.advanced_rl.domain import ReinforcementLearningConfig
        from app.contexts.advanced_rl.services.advanced_rl.engine import AdvancedReinforcementLearningEngine

        engine = AdvancedReinforcementLearningEngine()

        # Mock session and config
        mock_session_instance = MagicMock()
        config = ReinforcementLearningConfig(
            agent_id="test_agent", algorithm="ppo", hyperparameters={"learning_rate": 0.001, "batch_size": 32}
        )
        training_data = [{"state": [1, 2, 3], "action": 0, "reward": 1.0}]

        result = await engine.proximal_policy_optimization(mock_session_instance, config, training_data)

        assert "training_loss" in result
        assert "episode_rewards" in result

    @pytest.mark.skip(reason="torch operations too slow for CI")
    @patch("app.contexts.advanced_rl.services.advanced_rl.engine.Session")
    async def test_soft_actor_critic(self, mock_session):
        """Test SAC training"""
        from app.contexts.advanced_rl.domain import ReinforcementLearningConfig
        from app.contexts.advanced_rl.services.advanced_rl.engine import AdvancedReinforcementLearningEngine

        engine = AdvancedReinforcementLearningEngine()

        mock_session_instance = MagicMock()
        config = ReinforcementLearningConfig(
            agent_id="test_agent", algorithm="sac", hyperparameters={"learning_rate": 0.001, "batch_size": 32}
        )
        training_data = [{"state": [1, 2, 3], "action": 0, "reward": 1.0}]

        result = await engine.soft_actor_critic(mock_session_instance, config, training_data)

        assert "training_loss" in result
        assert "episode_rewards" in result
