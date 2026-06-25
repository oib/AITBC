"""
Tests for advanced RL agent modules
"""

import pytest
import torch


@pytest.mark.unit
class TestPPOAgent:
    """Test PPO Agent neural network"""

    def test_ppo_agent_initialization(self):
        """Test PPO agent initialization"""
        from app.contexts.advanced_rl.services.advanced_rl.agents.ppo_agent import PPOAgent

        agent = PPOAgent(state_dim=128, action_dim=10, hidden_dim=256)

        assert agent.actor is not None
        assert agent.critic is not None
        assert agent.actor[0].in_features == 128
        assert agent.actor[0].out_features == 256

    def test_ppo_agent_forward(self):
        """Test PPO agent forward pass"""
        from app.contexts.advanced_rl.services.advanced_rl.agents.ppo_agent import PPOAgent

        agent = PPOAgent(state_dim=128, action_dim=10, hidden_dim=256)
        state = torch.randn(1, 128)

        action_probs, value = agent(state)

        assert action_probs.shape == (1, 10)
        assert value.shape == (1, 1)
        assert torch.allclose(action_probs.sum(dim=1), torch.ones(1), atol=1e-5)  # Probabilities sum to 1


@pytest.mark.unit
class TestSACAgent:
    """Test SAC Agent neural network"""

    def test_sac_agent_initialization(self):
        """Test SAC agent initialization"""
        from app.contexts.advanced_rl.services.advanced_rl.agents.sac_agent import SACAgent

        agent = SACAgent(state_dim=128, action_dim=10, hidden_dim=256)

        assert agent.actor_mean is not None
        assert agent.actor_log_std is not None
        assert agent.qf1 is not None
        assert agent.qf2 is not None

    def test_sac_agent_forward(self):
        """Test SAC agent forward pass"""
        from app.contexts.advanced_rl.services.advanced_rl.agents.sac_agent import SACAgent

        agent = SACAgent(state_dim=128, action_dim=10, hidden_dim=256)
        state = torch.randn(1, 128)

        mean, std = agent(state)

        assert mean.shape == (1, 10)
        assert std.shape == (1, 10)
        assert (std >= 0).all()  # Standard deviation should be non-negative


@pytest.mark.unit
class TestRainbowDQNAgent:
    """Test Rainbow DQN Agent neural network"""

    def test_rainbow_dqn_agent_initialization(self):
        """Test Rainbow DQN agent initialization"""
        from app.contexts.advanced_rl.services.advanced_rl.agents.rainbow_dqn_agent import RainbowDQNAgent

        agent = RainbowDQNAgent(state_dim=128, action_dim=10, hidden_dim=512, num_atoms=51)

        assert agent.feature_layer is not None
        assert agent.value_stream is not None
        assert agent.advantage_stream is not None
        assert agent.num_atoms == 51

    def test_rainbow_dqn_agent_forward(self):
        """Test Rainbow DQN agent forward pass"""
        from app.contexts.advanced_rl.services.advanced_rl.agents.rainbow_dqn_agent import RainbowDQNAgent

        agent = RainbowDQNAgent(state_dim=128, action_dim=10, hidden_dim=512, num_atoms=51)
        state = torch.randn(1, 128)

        q_atoms = agent(state)

        assert q_atoms.shape == (1, 10, 51)
        assert q_atoms.shape[0] == 1  # Batch size
        assert q_atoms.shape[1] == 10  # Action dimension
        assert q_atoms.shape[2] == 51  # Number of atoms
