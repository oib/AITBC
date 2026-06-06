"""
Tests for advanced RL engine
"""

from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.mark.unit
class TestAdvancedReinforcementLearningEngine:
    """Test Advanced Reinforcement Learning Engine"""

    def test_engine_initialization(self):
        """Test engine initialization"""
        from app.services.advanced_rl.engine import AdvancedReinforcementLearningEngine

        engine = AdvancedReinforcementLearningEngine()

        assert engine.device is not None
        assert engine.agents == {}
        assert engine.training_histories == {}
        assert len(engine.rl_algorithms) > 0

    def test_load_agent(self):
        """Test loading an agent"""
        from app.services.advanced_rl.agents.ppo_agent import PPOAgent
        from app.services.advanced_rl.engine import AdvancedReinforcementLearningEngine

        engine = AdvancedReinforcementLearningEngine()
        agent_id = "test_agent"
        agent = PPOAgent(state_dim=128, action_dim=10)

        engine.load_agent(agent_id, agent)

        assert agent_id in engine.agents
        assert engine.agents[agent_id] == agent

    def test_select_action(self):
        """Test action selection"""
        import torch
        from app.services.advanced_rl.agents.ppo_agent import PPOAgent
        from app.services.advanced_rl.engine import AdvancedReinforcementLearningEngine

        engine = AdvancedReinforcementLearningEngine()
        agent_id = "test_agent"
        agent = PPOAgent(state_dim=128, action_dim=10)
        engine.load_agent(agent_id, agent)

        state = torch.randn(128)
        action = engine.select_action(agent_id, state)

        assert action is not None
        assert isinstance(action, (int, torch.Tensor))

    @patch('app.services.advanced_rl.engine.Session')
    async def test_proximal_policy_optimization(self, mock_session):
        """Test PPO training"""
        from app.domain.reinforcement_learning import ReinforcementLearningConfig
        from app.services.advanced_rl.engine import AdvancedReinforcementLearningEngine

        engine = AdvancedReinforcementLearningEngine()

        # Mock session and config
        mock_session_instance = MagicMock()
        config = ReinforcementLearningConfig(
            agent_id="test_agent",
            algorithm="ppo",
            hyperparameters={"learning_rate": 0.001, "batch_size": 32}
        )
        training_data = [{"state": [1, 2, 3], "action": 0, "reward": 1.0}]

        result = await engine.proximal_policy_optimization(mock_session_instance, config, training_data)

        assert "training_loss" in result
        assert "episode_rewards" in result

    @patch('app.services.advanced_rl.engine.Session')
    async def test_soft_actor_critic(self, mock_session):
        """Test SAC training"""
        from app.domain.reinforcement_learning import ReinforcementLearningConfig
        from app.services.advanced_rl.engine import AdvancedReinforcementLearningEngine

        engine = AdvancedReinforcementLearningEngine()

        mock_session_instance = MagicMock()
        config = ReinforcementLearningConfig(
            agent_id="test_agent",
            algorithm="sac",
            hyperparameters={"learning_rate": 0.001, "batch_size": 32}
        )
        training_data = [{"state": [1, 2, 3], "action": 0, "reward": 1.0}]

        result = await engine.soft_actor_critic(mock_session_instance, config, training_data)

        assert "training_loss" in result
        assert "episode_rewards" in result

    def test_evaluate_agent(self):
        """Test agent evaluation"""
        import torch
        from app.services.advanced_rl.agents.ppo_agent import PPOAgent
        from app.services.advanced_rl.engine import AdvancedReinforcementLearningEngine

        engine = AdvancedReinforcementLearningEngine()
        agent_id = "test_agent"
        agent = PPOAgent(state_dim=128, action_dim=10)
        engine.load_agent(agent_id, agent)

        eval_env = Mock()
        eval_env.reset.return_value = torch.randn(128)
        eval_env.step.return_value = (torch.randn(128), 1.0, False, {})

        result = engine.evaluate_agent(agent_id, eval_env, num_episodes=1)

        assert "average_reward" in result
        assert "success_rate" in result
