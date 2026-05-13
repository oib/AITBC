"""
Advanced Reinforcement Learning Service - Modular Implementation
Service facade for backward compatibility with the original monolithic file

This module provides a modular structure for RL algorithms:
- agents/: Neural network agent implementations (PPO, SAC, Rainbow DQN)
- engine.py: Main AdvancedReinforcementLearningEngine class
- marketplace_optimizer.py: Strategy optimization facade
- algorithms/: Algorithm-specific implementations (future enhancement)

The original advanced_reinforcement_learning.py has been deprecated in favor of this modular structure.
"""

from .engine import AdvancedReinforcementLearningEngine
from .marketplace_optimizer import MarketplaceStrategyOptimizer
from .agents import PPOAgent, SACAgent, RainbowDQNAgent

__all__ = [
    'AdvancedReinforcementLearningEngine',
    'MarketplaceStrategyOptimizer',
    'PPOAgent',
    'SACAgent',
    'RainbowDQNAgent',
]
