"""
Advanced Reinforcement Learning Service - Modular Implementation
Service facade for backward compatibility with the original monolithic file

This module provides a modular structure for RL algorithms:
- agents/: Neural network agent implementations (PPO, SAC, Rainbow DQN)
- engine.py: Main AdvancedReinforcementLearningEngine class
- market_optimizer.py: Strategy optimization facade
- algorithms/: Algorithm-specific implementations (future enhancement)

The original advanced_reinforcement_learning.py has been deprecated in favor of this modular structure.
"""

from .agents import PPOAgent, RainbowDQNAgent, SACAgent
from .engine import AdvancedReinforcementLearningEngine
from .market_optimizer import MarketStrategyOptimizer

__all__ = [
    "AdvancedReinforcementLearningEngine",
    "MarketStrategyOptimizer",
    "PPOAgent",
    "SACAgent",
    "RainbowDQNAgent",
]
