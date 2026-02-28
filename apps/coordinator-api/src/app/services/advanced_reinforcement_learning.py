"""
Advanced Reinforcement Learning Service
Implements sophisticated RL algorithms for marketplace strategies and agent optimization
"""

import asyncio
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
from aitbc.logging import get_logger

from sqlmodel import Session, select, update, delete, and_, or_, func
from sqlalchemy.exc import SQLAlchemyError

from ..domain.agent_performance import (
    ReinforcementLearningConfig, AgentPerformanceProfile,
    AgentCapability, FusionModel
)

logger = get_logger(__name__)


class AdvancedReinforcementLearningEngine:
    """Advanced RL engine for marketplace strategies"""
    
    def __init__(self):
        self.rl_algorithms = {
            'ppo': self.proximal_policy_optimization,
            'a2c': self.advantage_actor_critic,
            'dqn': self.deep_q_network,
            'sac': self.soft_actor_critic,
            'td3': self.twin_delayed_ddpg,
            'rainbow_dqn': self.rainbow_dqn,
            'impala': self.impala,
            'muzero': self.muzero
        }
        
        self.environment_types = {
            'marketplace_trading': self.marketplace_trading_env,
            'resource_allocation': self.resource_allocation_env,
            'price_optimization': self.price_optimization_env,
            'service_selection': self.service_selection_env,
            'negotiation_strategy': self.negotiation_strategy_env,
            'portfolio_management': self.portfolio_management_env
        }
        
        self.state_spaces = {
            'market_state': ['price', 'volume', 'demand', 'supply', 'competition'],
            'agent_state': ['reputation', 'resources', 'capabilities', 'position'],
            'economic_state': ['inflation', 'growth', 'volatility', 'trends']
        }
        
        self.action_spaces = {
            'pricing': ['increase', 'decrease', 'maintain', 'dynamic'],
            'resource': ['allocate', 'reallocate', 'optimize', 'scale'],
            'strategy': ['aggressive', 'conservative', 'balanced', 'adaptive'],
            'timing': ['immediate', 'delayed', 'batch', 'continuous']
        }
    
    async def create_rl_agent(
        self, 
        session: Session,
        agent_id: str,
        environment_type: str,
        algorithm: str = "ppo",
        training_config: Optional[Dict[str, Any]] = None
    ) -> ReinforcementLearningConfig:
        """Create a new RL agent for marketplace strategies"""
        
        config_id = f"rl_{uuid4().hex[:8]}"
        
        # Set default training configuration
        default_config = {
            'learning_rate': 0.001,
            'discount_factor': 0.99,
            'exploration_rate': 0.1,
            'batch_size': 64,
            'max_episodes': 1000,
            'max_steps_per_episode': 1000,
            'save_frequency': 100
        }
        
        if training_config:
            default_config.update(training_config)
        
        # Configure network architecture based on environment
        network_config = self.configure_network_architecture(environment_type, algorithm)
        
        rl_config = ReinforcementLearningConfig(
            config_id=config_id,
            agent_id=agent_id,
            environment_type=environment_type,
            algorithm=algorithm,
            learning_rate=default_config['learning_rate'],
            discount_factor=default_config['discount_factor'],
            exploration_rate=default_config['exploration_rate'],
            batch_size=default_config['batch_size'],
            network_layers=network_config['layers'],
            activation_functions=network_config['activations'],
            max_episodes=default_config['max_episodes'],
            max_steps_per_episode=default_config['max_steps_per_episode'],
            save_frequency=default_config['save_frequency'],
            action_space=self.get_action_space(environment_type),
            state_space=self.get_state_space(environment_type),
            status="training"
        )
        
        session.add(rl_config)
        session.commit()
        session.refresh(rl_config)
        
        # Start training process
        asyncio.create_task(self.train_rl_agent(session, config_id))
        
        logger.info(f"Created RL agent {config_id} with algorithm {algorithm}")
        return rl_config
    
    async def train_rl_agent(self, session: Session, config_id: str) -> Dict[str, Any]:
        """Train RL agent"""
        
        rl_config = session.exec(
            select(ReinforcementLearningConfig).where(ReinforcementLearningConfig.config_id == config_id)
        ).first()
        
        if not rl_config:
            raise ValueError(f"RL config {config_id} not found")
        
        try:
            # Get training algorithm
            algorithm_func = self.rl_algorithms.get(rl_config.algorithm)
            if not algorithm_func:
                raise ValueError(f"Unknown RL algorithm: {rl_config.algorithm}")
            
            # Get environment
            environment_func = self.environment_types.get(rl_config.environment_type)
            if not environment_func:
                raise ValueError(f"Unknown environment type: {rl_config.environment_type}")
            
            # Train the agent
            training_results = await algorithm_func(rl_config, environment_func)
            
            # Update config with training results
            rl_config.reward_history = training_results['reward_history']
            rl_config.success_rate_history = training_results['success_rate_history']
            rl_config.convergence_episode = training_results['convergence_episode']
            rl_config.status = "ready"
            rl_config.trained_at = datetime.utcnow()
            rl_config.training_progress = 1.0
            
            session.commit()
            
            logger.info(f"RL agent {config_id} training completed")
            return training_results
            
        except Exception as e:
            logger.error(f"Error training RL agent {config_id}: {str(e)}")
            rl_config.status = "failed"
            session.commit()
            raise
    
    async def proximal_policy_optimization(
        self, 
        config: ReinforcementLearningConfig, 
        environment_func
    ) -> Dict[str, Any]:
        """Proximal Policy Optimization algorithm"""
        
        # Simulate PPO training
        reward_history = []
        success_rate_history = []
        
        # Training parameters
        clip_ratio = 0.2
        value_loss_coef = 0.5
        entropy_coef = 0.01
        max_grad_norm = 0.5
        
        # Simulate training episodes
        for episode in range(config.max_episodes):
            episode_reward = 0.0
            episode_success = 0.0
            
            # Simulate episode steps
            for step in range(config.max_steps_per_episode):
                # Get state and action
                state = self.get_random_state(config.state_space)
                action = self.select_action(state, config.action_space)
                
                # Take action in environment
                next_state, reward, done, info = await self.simulate_environment_step(
                    environment_func, state, action, config.environment_type
                )
                
                episode_reward += reward
                if info.get('success', False):
                    episode_success += 1.0
                
                if done:
                    break
            
            # Calculate episode metrics
            avg_reward = episode_reward / config.max_steps_per_episode
            success_rate = episode_success / config.max_steps_per_episode
            
            reward_history.append(avg_reward)
            success_rate_history.append(success_rate)
            
            # Check for convergence
            if len(reward_history) > 100 and np.mean(reward_history[-50:]) > 0.8:
                break
        
        convergence_episode = len(reward_history)
        
        return {
            'reward_history': reward_history,
            'success_rate_history': success_rate_history,
            'convergence_episode': convergence_episode,
            'final_performance': np.mean(reward_history[-10:]) if reward_history else 0.0,
            'training_time': len(reward_history) * 0.1  # hours
        }
    
    async def advantage_actor_critic(
        self, 
        config: ReinforcementLearningConfig, 
        environment_func
    ) -> Dict[str, Any]:
        """Advantage Actor-Critic algorithm"""
        
        # Simulate A2C training
        reward_history = []
        success_rate_history = []
        
        # A2C specific parameters
        value_loss_coef = 0.5
        entropy_coef = 0.01
        max_grad_norm = 0.5
        
        for episode in range(config.max_episodes):
            episode_reward = 0.0
            episode_success = 0.0
            
            for step in range(config.max_steps_per_episode):
                state = self.get_random_state(config.state_space)
                action = self.select_action(state, config.action_space)
                
                next_state, reward, done, info = await self.simulate_environment_step(
                    environment_func, state, action, config.environment_type
                )
                
                episode_reward += reward
                if info.get('success', False):
                    episode_success += 1.0
                
                if done:
                    break
            
            avg_reward = episode_reward / config.max_steps_per_episode
            success_rate = episode_success / config.max_steps_per_episode
            
            reward_history.append(avg_reward)
            success_rate_history.append(success_rate)
            
            # A2C convergence check
            if len(reward_history) > 80 and np.mean(reward_history[-40:]) > 0.75:
                break
        
        convergence_episode = len(reward_history)
        
        return {
            'reward_history': reward_history,
            'success_rate_history': success_rate_history,
            'convergence_episode': convergence_episode,
            'final_performance': np.mean(reward_history[-10:]) if reward_history else 0.0,
            'training_time': len(reward_history) * 0.08
        }
    
    async def deep_q_network(
        self, 
        config: ReinforcementLearningConfig, 
        environment_func
    ) -> Dict[str, Any]:
        """Deep Q-Network algorithm"""
        
        # Simulate DQN training
        reward_history = []
        success_rate_history = []
        
        # DQN specific parameters
        epsilon_start = 1.0
        epsilon_end = 0.01
        epsilon_decay = 0.995
        target_update_freq = 1000
        
        epsilon = epsilon_start
        
        for episode in range(config.max_episodes):
            episode_reward = 0.0
            episode_success = 0.0
            
            for step in range(config.max_steps_per_episode):
                state = self.get_random_state(config.state_space)
                
                # Epsilon-greedy action selection
                if np.random.random() < epsilon:
                    action = np.random.choice(config.action_space)
                else:
                    action = self.select_action(state, config.action_space)
                
                next_state, reward, done, info = await self.simulate_environment_step(
                    environment_func, state, action, config.environment_type
                )
                
                episode_reward += reward
                if info.get('success', False):
                    episode_success += 1.0
                
                if done:
                    break
            
            # Decay epsilon
            epsilon = max(epsilon_end, epsilon * epsilon_decay)
            
            avg_reward = episode_reward / config.max_steps_per_episode
            success_rate = episode_success / config.max_steps_per_episode
            
            reward_history.append(avg_reward)
            success_rate_history.append(success_rate)
            
            # DQN convergence check
            if len(reward_history) > 120 and np.mean(reward_history[-60:]) > 0.7:
                break
        
        convergence_episode = len(reward_history)
        
        return {
            'reward_history': reward_history,
            'success_rate_history': success_rate_history,
            'convergence_episode': convergence_episode,
            'final_performance': np.mean(reward_history[-10:]) if reward_history else 0.0,
            'training_time': len(reward_history) * 0.12
        }
    
    async def soft_actor_critic(
        self, 
        config: ReinforcementLearningConfig, 
        environment_func
    ) -> Dict[str, Any]:
        """Soft Actor-Critic algorithm"""
        
        # Simulate SAC training
        reward_history = []
        success_rate_history = []
        
        # SAC specific parameters
        alpha = 0.2  # Temperature parameter
        tau = 0.005  # Soft update parameter
        target_entropy = -np.prod(10)  # Target entropy
        
        for episode in range(config.max_episodes):
            episode_reward = 0.0
            episode_success = 0.0
            
            for step in range(config.max_steps_per_episode):
                state = self.get_random_state(config.state_space)
                action = self.select_action(state, config.action_space)
                
                next_state, reward, done, info = await self.simulate_environment_step(
                    environment_func, state, action, config.environment_type
                )
                
                episode_reward += reward
                if info.get('success', False):
                    episode_success += 1.0
                
                if done:
                    break
            
            avg_reward = episode_reward / config.max_steps_per_episode
            success_rate = episode_success / config.max_steps_per_episode
            
            reward_history.append(avg_reward)
            success_rate_history.append(success_rate)
            
            # SAC convergence check
            if len(reward_history) > 90 and np.mean(reward_history[-45:]) > 0.85:
                break
        
        convergence_episode = len(reward_history)
        
        return {
            'reward_history': reward_history,
            'success_rate_history': success_rate_history,
            'convergence_episode': convergence_episode,
            'final_performance': np.mean(reward_history[-10:]) if reward_history else 0.0,
            'training_time': len(reward_history) * 0.15
        }
    
    async def twin_delayed_ddpg(
        self, 
        config: ReinforcementLearningConfig, 
        environment_func
    ) -> Dict[str, Any]:
        """Twin Delayed DDPG algorithm"""
        
        # Simulate TD3 training
        reward_history = []
        success_rate_history = []
        
        # TD3 specific parameters
        policy_noise = 0.2
        noise_clip = 0.5
        policy_delay = 2
        tau = 0.005
        
        for episode in range(config.max_episodes):
            episode_reward = 0.0
            episode_success = 0.0
            
            for step in range(config.max_steps_per_episode):
                state = self.get_random_state(config.state_space)
                action = self.select_action(state, config.action_space)
                
                next_state, reward, done, info = await self.simulate_environment_step(
                    environment_func, state, action, config.environment_type
                )
                
                episode_reward += reward
                if info.get('success', False):
                    episode_success += 1.0
                
                if done:
                    break
            
            avg_reward = episode_reward / config.max_steps_per_episode
            success_rate = episode_success / config.max_steps_per_episode
            
            reward_history.append(avg_reward)
            success_rate_history.append(success_rate)
            
            # TD3 convergence check
            if len(reward_history) > 110 and np.mean(reward_history[-55:]) > 0.82:
                break
        
        convergence_episode = len(reward_history)
        
        return {
            'reward_history': reward_history,
            'success_rate_history': success_rate_history,
            'convergence_episode': convergence_episode,
            'final_performance': np.mean(reward_history[-10:]) if reward_history else 0.0,
            'training_time': len(reward_history) * 0.18
        }
    
    async def rainbow_dqn(
        self, 
        config: ReinforcementLearningConfig, 
        environment_func
    ) -> Dict[str, Any]:
        """Rainbow DQN algorithm"""
        
        # Simulate Rainbow DQN training
        reward_history = []
        success_rate_history = []
        
        # Rainbow DQN combines multiple improvements
        for episode in range(config.max_episodes):
            episode_reward = 0.0
            episode_success = 0.0
            
            for step in range(config.max_steps_per_episode):
                state = self.get_random_state(config.state_space)
                action = self.select_action(state, config.action_space)
                
                next_state, reward, done, info = await self.simulate_environment_step(
                    environment_func, state, action, config.environment_type
                )
                
                episode_reward += reward
                if info.get('success', False):
                    episode_success += 1.0
                
                if done:
                    break
            
            avg_reward = episode_reward / config.max_steps_per_episode
            success_rate = episode_success / config.max_steps_per_episode
            
            reward_history.append(avg_reward)
            success_rate_history.append(success_rate)
            
            # Rainbow DQN convergence check
            if len(reward_history) > 100 and np.mean(reward_history[-50:]) > 0.88:
                break
        
        convergence_episode = len(reward_history)
        
        return {
            'reward_history': reward_history,
            'success_rate_history': success_rate_history,
            'convergence_episode': convergence_episode,
            'final_performance': np.mean(reward_history[-10:]) if reward_history else 0.0,
            'training_time': len(reward_history) * 0.20
        }
    
    async def impala(
        self, 
        config: ReinforcementLearningConfig, 
        environment_func
    ) -> Dict[str, Any]:
        """IMPALA algorithm"""
        
        # Simulate IMPALA training
        reward_history = []
        success_rate_history = []
        
        # IMPALA specific parameters
        rollout_length = 50
        discount_factor = 0.99
        entropy_coef = 0.01
        
        for episode in range(config.max_episodes):
            episode_reward = 0.0
            episode_success = 0.0
            
            for step in range(config.max_steps_per_episode):
                state = self.get_random_state(config.state_space)
                action = self.select_action(state, config.action_space)
                
                next_state, reward, done, info = await self.simulate_environment_step(
                    environment_func, state, action, config.environment_type
                )
                
                episode_reward += reward
                if info.get('success', False):
                    episode_success += 1.0
                
                if done:
                    break
            
            avg_reward = episode_reward / config.max_steps_per_episode
            success_rate = episode_success / config.max_steps_per_episode
            
            reward_history.append(avg_reward)
            success_rate_history.append(success_rate)
            
            # IMPALA convergence check
            if len(reward_history) > 80 and np.mean(reward_history[-40:]) > 0.83:
                break
        
        convergence_episode = len(reward_history)
        
        return {
            'reward_history': reward_history,
            'success_rate_history': success_rate_history,
            'convergence_episode': convergence_episode,
            'final_performance': np.mean(reward_history[-10:]) if reward_history else 0.0,
            'training_time': len(reward_history) * 0.25
        }
    
    async def muzero(
        self, 
        config: ReinforcementLearningConfig, 
        environment_func
    ) -> Dict[str, Any]:
        """MuZero algorithm"""
        
        # Simulate MuZero training
        reward_history = []
        success_rate_history = []
        
        # MuZero specific parameters
        num_simulations = 50
        discount_factor = 0.99
        td_steps = 5
        
        for episode in range(config.max_episodes):
            episode_reward = 0.0
            episode_success = 0.0
            
            for step in range(config.max_steps_per_episode):
                state = self.get_random_state(config.state_space)
                action = self.select_action(state, config.action_space)
                
                next_state, reward, done, info = await self.simulate_environment_step(
                    environment_func, state, action, config.environment_type
                )
                
                episode_reward += reward
                if info.get('success', False):
                    episode_success += 1.0
                
                if done:
                    break
            
            avg_reward = episode_reward / config.max_steps_per_episode
            success_rate = episode_success / config.max_steps_per_episode
            
            reward_history.append(avg_reward)
            success_rate_history.append(success_rate)
            
            # MuZero convergence check
            if len(reward_history) > 70 and np.mean(reward_history[-35:]) > 0.9:
                break
        
        convergence_episode = len(reward_history)
        
        return {
            'reward_history': reward_history,
            'success_rate_history': success_rate_history,
            'convergence_episode': convergence_episode,
            'final_performance': np.mean(reward_history[-10:]) if reward_history else 0.0,
            'training_time': len(reward_history) * 0.30
        }
    
    def configure_network_architecture(self, environment_type: str, algorithm: str) -> Dict[str, Any]:
        """Configure network architecture for RL agent"""
        
        # Base configurations
        base_configs = {
            'marketplace_trading': {
                'layers': [256, 256, 128, 64],
                'activations': ['relu', 'relu', 'tanh', 'linear']
            },
            'resource_allocation': {
                'layers': [512, 256, 128, 64],
                'activations': ['relu', 'relu', 'relu', 'linear']
            },
            'price_optimization': {
                'layers': [128, 128, 64, 32],
                'activations': ['tanh', 'relu', 'tanh', 'linear']
            },
            'service_selection': {
                'layers': [256, 128, 64, 32],
                'activations': ['relu', 'tanh', 'relu', 'linear']
            },
            'negotiation_strategy': {
                'layers': [512, 256, 128, 64],
                'activations': ['relu', 'relu', 'tanh', 'linear']
            },
            'portfolio_management': {
                'layers': [1024, 512, 256, 128],
                'activations': ['relu', 'relu', 'relu', 'linear']
            }
        }
        
        config = base_configs.get(environment_type, base_configs['marketplace_trading'])
        
        # Adjust for algorithm-specific requirements
        if algorithm in ['sac', 'td3']:
            # Actor-Critic algorithms need separate networks
            config['actor_layers'] = config['layers'][:-1]
            config['critic_layers'] = config['layers']
        elif algorithm == 'muzero':
            # MuZero needs representation and dynamics networks
            config['representation_layers'] = [256, 256, 128]
            config['dynamics_layers'] = [256, 256, 128]
            config['prediction_layers'] = config['layers']
        
        return config
    
    def get_action_space(self, environment_type: str) -> List[str]:
        """Get action space for environment type"""
        
        action_spaces = {
            'marketplace_trading': ['buy', 'sell', 'hold', 'bid', 'ask'],
            'resource_allocation': ['allocate', 'reallocate', 'optimize', 'scale'],
            'price_optimization': ['increase', 'decrease', 'maintain', 'dynamic'],
            'service_selection': ['select', 'reject', 'defer', 'bundle'],
            'negotiation_strategy': ['accept', 'reject', 'counter', 'propose'],
            'portfolio_management': ['invest', 'divest', 'rebalance', 'hold']
        }
        
        return action_spaces.get(environment_type, ['action_1', 'action_2', 'action_3'])
    
    def get_state_space(self, environment_type: str) -> List[str]:
        """Get state space for environment type"""
        
        state_spaces = {
            'marketplace_trading': ['price', 'volume', 'demand', 'supply', 'competition'],
            'resource_allocation': ['available', 'utilized', 'cost', 'efficiency', 'demand'],
            'price_optimization': ['current_price', 'market_price', 'demand', 'competition', 'cost'],
            'service_selection': ['requirements', 'availability', 'quality', 'price', 'reputation'],
            'negotiation_strategy': ['position', 'offer', 'deadline', 'market_state', 'leverage'],
            'portfolio_management': ['holdings', 'value', 'risk', 'performance', 'allocation']
        }
        
        return state_spaces.get(environment_type, ['state_1', 'state_2', 'state_3'])
    
    def get_random_state(self, state_space: List[str]) -> Dict[str, float]:
        """Generate random state for simulation"""
        
        return {state: np.random.uniform(0, 1) for state in state_space}
    
    def select_action(self, state: Dict[str, float], action_space: List[str]) -> str:
        """Select action based on state (simplified)"""
        
        # Simple policy: select action based on state values
        state_sum = sum(state.values())
        action_index = int(state_sum * len(action_space)) % len(action_space)
        return action_space[action_index]
    
    async def simulate_environment_step(
        self, 
        environment_func, 
        state: Dict[str, float], 
        action: str, 
        environment_type: str
    ) -> Tuple[Dict[str, float], float, bool, Dict[str, Any]]:
        """Simulate environment step"""
        
        # Get environment
        env = environment_func()
        
        # Simulate step
        next_state = self.get_next_state(state, action, environment_type)
        reward = self.calculate_reward(state, action, next_state, environment_type)
        done = self.check_done(next_state, environment_type)
        info = self.get_step_info(state, action, next_state, environment_type)
        
        return next_state, reward, done, info
    
    def get_next_state(self, state: Dict[str, float], action: str, environment_type: str) -> Dict[str, float]:
        """Get next state after action"""
        
        next_state = {}
        
        for key, value in state.items():
            # Apply state transition based on action
            if action in ['buy', 'invest', 'allocate']:
                change = np.random.uniform(-0.1, 0.2)
            elif action in ['sell', 'divest', 'reallocate']:
                change = np.random.uniform(-0.2, 0.1)
            else:
                change = np.random.uniform(-0.05, 0.05)
            
            next_state[key] = np.clip(value + change, 0, 1)
        
        return next_state
    
    def calculate_reward(self, state: Dict[str, float], action: str, next_state: Dict[str, float], environment_type: str) -> float:
        """Calculate reward for state-action-next_state transition"""
        
        # Base reward calculation
        if environment_type == 'marketplace_trading':
            if action == 'buy' and next_state.get('price', 0) < state.get('price', 0):
                return 1.0  # Good buy
            elif action == 'sell' and next_state.get('price', 0) > state.get('price', 0):
                return 1.0  # Good sell
            else:
                return -0.1  # Small penalty
        
        elif environment_type == 'resource_allocation':
            efficiency_gain = next_state.get('efficiency', 0) - state.get('efficiency', 0)
            return efficiency_gain * 2.0  # Reward efficiency improvement
        
        elif environment_type == 'price_optimization':
            demand_match = abs(next_state.get('demand', 0) - next_state.get('price', 0))
            return -demand_match  # Minimize demand-price mismatch
        
        else:
            # Generic reward
            improvement = sum(next_state.values()) - sum(state.values())
            return improvement * 0.5
    
    def check_done(self, state: Dict[str, float], environment_type: str) -> bool:
        """Check if episode is done"""
        
        # Episode termination conditions
        if environment_type == 'marketplace_trading':
            return state.get('volume', 0) > 0.9 or state.get('competition', 0) > 0.8
        
        elif environment_type == 'resource_allocation':
            return state.get('utilized', 0) > 0.95 or state.get('cost', 0) > 0.9
        
        else:
            # Random termination with low probability
            return np.random.random() < 0.05
    
    def get_step_info(self, state: Dict[str, float], action: str, next_state: Dict[str, float], environment_type: str) -> Dict[str, Any]:
        """Get step information"""
        
        info = {
            'action': action,
            'state_change': sum(next_state.values()) - sum(state.values()),
            'environment_type': environment_type
        }
        
        # Add environment-specific info
        if environment_type == 'marketplace_trading':
            info['success'] = next_state.get('price', 0) > state.get('price', 0) and action == 'sell'
            info['profit'] = next_state.get('price', 0) - state.get('price', 0)
        
        elif environment_type == 'resource_allocation':
            info['success'] = next_state.get('efficiency', 0) > state.get('efficiency', 0)
            info['efficiency_gain'] = next_state.get('efficiency', 0) - state.get('efficiency', 0)
        
        return info
    
    # Environment functions
    def marketplace_trading_env(self):
        """Marketplace trading environment"""
        return {
            'name': 'marketplace_trading',
            'description': 'AI power trading environment',
            'max_episodes': 1000,
            'max_steps': 500
        }
    
    def resource_allocation_env(self):
        """Resource allocation environment"""
        return {
            'name': 'resource_allocation',
            'description': 'Resource optimization environment',
            'max_episodes': 800,
            'max_steps': 300
        }
    
    def price_optimization_env(self):
        """Price optimization environment"""
        return {
            'name': 'price_optimization',
            'description': 'Dynamic pricing environment',
            'max_episodes': 600,
            'max_steps': 200
        }
    
    def service_selection_env(self):
        """Service selection environment"""
        return {
            'name': 'service_selection',
            'description': 'Service selection environment',
            'max_episodes': 700,
            'max_steps': 250
        }
    
    def negotiation_strategy_env(self):
        """Negotiation strategy environment"""
        return {
            'name': 'negotiation_strategy',
            'description': 'Negotiation strategy environment',
            'max_episodes': 900,
            'max_steps': 400
        }
    
    def portfolio_management_env(self):
        """Portfolio management environment"""
        return {
            'name': 'portfolio_management',
            'description': 'Portfolio management environment',
            'max_episodes': 1200,
            'max_steps': 600
        }


class MarketplaceStrategyOptimizer:
    """Advanced marketplace strategy optimization using RL"""
    
    def __init__(self):
        self.rl_engine = AdvancedReinforcementLearningEngine()
        self.strategy_types = {
            'pricing_strategy': 'price_optimization',
            'trading_strategy': 'marketplace_trading',
            'resource_strategy': 'resource_allocation',
            'service_strategy': 'service_selection',
            'negotiation_strategy': 'negotiation_strategy',
            'portfolio_strategy': 'portfolio_management'
        }
    
    async def optimize_agent_strategy(
        self, 
        session: Session,
        agent_id: str,
        strategy_type: str,
        algorithm: str = "ppo",
        training_episodes: int = 500
    ) -> Dict[str, Any]:
        """Optimize agent strategy using RL"""
        
        # Get environment type for strategy
        environment_type = self.strategy_types.get(strategy_type, 'marketplace_trading')
        
        # Create RL agent
        rl_config = await self.rl_engine.create_rl_agent(
            session=session,
            agent_id=agent_id,
            environment_type=environment_type,
            algorithm=algorithm,
            training_config={'max_episodes': training_episodes}
        )
        
        # Wait for training to complete
        await asyncio.sleep(1)  # Simulate training time
        
        # Get trained agent performance
        trained_config = session.exec(
            select(ReinforcementLearningConfig).where(
                ReinforcementLearningConfig.config_id == rl_config.config_id
            )
        ).first()
        
        if trained_config and trained_config.status == "ready":
            return {
                'success': True,
                'config_id': trained_config.config_id,
                'strategy_type': strategy_type,
                'algorithm': algorithm,
                'final_performance': np.mean(trained_config.reward_history[-10:]) if trained_config.reward_history else 0.0,
                'convergence_episode': trained_config.convergence_episode,
                'training_episodes': len(trained_config.reward_history),
                'success_rate': np.mean(trained_config.success_rate_history[-10:]) if trained_config.success_rate_history else 0.0
            }
        else:
            return {
                'success': False,
                'error': 'Training failed or incomplete'
            }
    
    async def deploy_strategy(
        self, 
        session: Session,
        config_id: str,
        deployment_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deploy trained strategy"""
        
        rl_config = session.exec(
            select(ReinforcementLearningConfig).where(
                ReinforcementLearningConfig.config_id == config_id
            )
        ).first()
        
        if not rl_config:
            raise ValueError(f"RL config {config_id} not found")
        
        if rl_config.status != "ready":
            raise ValueError(f"Strategy {config_id} is not ready for deployment")
        
        try:
            # Update deployment performance
            deployment_performance = self.simulate_deployment_performance(rl_config, deployment_context)
            
            rl_config.deployment_performance = deployment_performance
            rl_config.deployment_count += 1
            rl_config.status = "deployed"
            rl_config.deployed_at = datetime.utcnow()
            
            session.commit()
            
            return {
                'success': True,
                'config_id': config_id,
                'deployment_performance': deployment_performance,
                'deployed_at': rl_config.deployed_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error deploying strategy {config_id}: {str(e)}")
            raise
    
    def simulate_deployment_performance(self, rl_config: ReinforcementLearningConfig, context: Dict[str, Any]) -> Dict[str, float]:
        """Simulate deployment performance"""
        
        # Base performance from training
        base_performance = np.mean(rl_config.reward_history[-10:]) if rl_config.reward_history else 0.5
        
        # Adjust based on deployment context
        context_factor = context.get('market_conditions', 1.0)
        complexity_factor = context.get('task_complexity', 1.0)
        
        # Calculate deployment metrics
        deployment_performance = {
            'accuracy': min(1.0, base_performance * context_factor),
            'efficiency': min(1.0, base_performance * 0.9 / complexity_factor),
            'adaptability': min(1.0, base_performance * 0.85),
            'robustness': min(1.0, base_performance * 0.8),
            'scalability': min(1.0, base_performance * 0.75)
        }
        
        return deployment_performance


class CrossDomainCapabilityIntegrator:
    """Cross-domain capability integration system"""
    
    def __init__(self):
        self.capability_domains = {
            'cognitive': ['reasoning', 'planning', 'problem_solving', 'decision_making'],
            'creative': ['generation', 'innovation', 'design', 'artistic'],
            'analytical': ['analysis', 'prediction', 'optimization', 'modeling'],
            'technical': ['implementation', 'engineering', 'architecture', 'optimization'],
            'social': ['communication', 'collaboration', 'negotiation', 'leadership']
        }
        
        self.integration_strategies = {
            'sequential': self.sequential_integration,
            'parallel': self.parallel_integration,
            'hierarchical': self.hierarchical_integration,
            'adaptive': self.adaptive_integration,
            'ensemble': self.ensemble_integration
        }
    
    async def integrate_cross_domain_capabilities(
        self, 
        session: Session,
        agent_id: str,
        capabilities: List[str],
        integration_strategy: str = "adaptive"
    ) -> Dict[str, Any]:
        """Integrate capabilities across different domains"""
        
        # Get agent capabilities
        agent_capabilities = session.exec(
            select(AgentCapability).where(AgentCapability.agent_id == agent_id)
        ).all()
        
        if not agent_capabilities:
            raise ValueError(f"No capabilities found for agent {agent_id}")
        
        # Group capabilities by domain
        domain_capabilities = self.group_capabilities_by_domain(agent_capabilities)
        
        # Apply integration strategy
        integration_func = self.integration_strategies.get(integration_strategy, self.adaptive_integration)
        integration_result = await integration_func(domain_capabilities, capabilities)
        
        # Create fusion model for integrated capabilities
        fusion_model = await self.create_capability_fusion_model(
            session, agent_id, domain_capabilities, integration_strategy
        )
        
        return {
            'agent_id': agent_id,
            'integration_strategy': integration_strategy,
            'domain_capabilities': domain_capabilities,
            'integration_result': integration_result,
            'fusion_model_id': fusion_model.fusion_id,
            'synergy_score': integration_result.get('synergy_score', 0.0),
            'enhanced_capabilities': integration_result.get('enhanced_capabilities', [])
        }
    
    def group_capabilities_by_domain(self, capabilities: List[AgentCapability]) -> Dict[str, List[AgentCapability]]:
        """Group capabilities by domain"""
        
        domain_groups = {}
        
        for capability in capabilities:
            domain = self.get_capability_domain(capability.capability_type)
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(capability)
        
        return domain_groups
    
    def get_capability_domain(self, capability_type: str) -> str:
        """Get domain for capability type"""
        
        domain_mapping = {
            'cognitive': 'cognitive',
            'creative': 'creative',
            'analytical': 'analytical',
            'technical': 'technical',
            'social': 'social'
        }
        
        return domain_mapping.get(capability_type, 'general')
    
    async def sequential_integration(
        self, 
        domain_capabilities: Dict[str, List[AgentCapability]], 
        target_capabilities: List[str]
    ) -> Dict[str, Any]:
        """Sequential integration strategy"""
        
        integration_result = {
            'strategy': 'sequential',
            'synergy_score': 0.0,
            'enhanced_capabilities': [],
            'integration_order': []
        }
        
        # Order domains by capability strength
        ordered_domains = self.order_domains_by_strength(domain_capabilities)
        
        # Sequentially integrate capabilities
        current_capabilities = []
        
        for domain in ordered_domains:
            if domain in domain_capabilities:
                domain_caps = domain_capabilities[domain]
                enhanced_caps = self.enhance_capabilities_sequentially(domain_caps, current_capabilities)
                current_capabilities.extend(enhanced_caps)
                integration_result['integration_order'].append(domain)
        
        # Calculate synergy score
        integration_result['synergy_score'] = self.calculate_sequential_synergy(current_capabilities)
        integration_result['enhanced_capabilities'] = [cap.capability_name for cap in current_capabilities]
        
        return integration_result
    
    async def parallel_integration(
        self, 
        domain_capabilities: Dict[str, List[AgentCapability]], 
        target_capabilities: List[str]
    ) -> Dict[str, Any]:
        """Parallel integration strategy"""
        
        integration_result = {
            'strategy': 'parallel',
            'synergy_score': 0.0,
            'enhanced_capabilities': [],
            'parallel_domains': []
        }
        
        # Process all domains in parallel
        all_capabilities = []
        
        for domain, capabilities in domain_capabilities.items():
            enhanced_caps = self.enhance_capabilities_in_parallel(capabilities)
            all_capabilities.extend(enhanced_caps)
            integration_result['parallel_domains'].append(domain)
        
        # Calculate synergy score
        integration_result['synergy_score'] = self.calculate_parallel_synergy(all_capabilities)
        integration_result['enhanced_capabilities'] = [cap.capability_name for cap in all_capabilities]
        
        return integration_result
    
    async def hierarchical_integration(
        self, 
        domain_capabilities: Dict[str, List[AgentCapability]], 
        target_capabilities: List[str]
    ) -> Dict[str, Any]:
        """Hierarchical integration strategy"""
        
        integration_result = {
            'strategy': 'hierarchical',
            'synergy_score': 0.0,
            'enhanced_capabilities': [],
            'hierarchy_levels': []
        }
        
        # Build hierarchy levels
        hierarchy = self.build_capability_hierarchy(domain_capabilities)
        
        # Integrate from bottom to top
        integrated_capabilities = []
        
        for level in hierarchy:
            level_capabilities = self.enhance_capabilities_hierarchically(level)
            integrated_capabilities.extend(level_capabilities)
            integration_result['hierarchy_levels'].append(len(level))
        
        # Calculate synergy score
        integration_result['synergy_score'] = self.calculate_hierarchical_synergy(integrated_capabilities)
        integration_result['enhanced_capabilities'] = [cap.capability_name for cap in integrated_capabilities]
        
        return integration_result
    
    async def adaptive_integration(
        self, 
        domain_capabilities: Dict[str, List[AgentCapability]], 
        target_capabilities: List[str]
    ) -> Dict[str, Any]:
        """Adaptive integration strategy"""
        
        integration_result = {
            'strategy': 'adaptive',
            'synergy_score': 0.0,
            'enhanced_capabilities': [],
            'adaptation_decisions': []
        }
        
        # Analyze capability compatibility
        compatibility_matrix = self.analyze_capability_compatibility(domain_capabilities)
        
        # Adaptively integrate based on compatibility
        integrated_capabilities = []
        
        for domain, capabilities in domain_capabilities.items():
            compatibility_score = compatibility_matrix.get(domain, 0.5)
            
            if compatibility_score > 0.7:
                # High compatibility - full integration
                enhanced_caps = self.enhance_capabilities_fully(capabilities)
                integration_result['adaptation_decisions'].append(f"Full integration for {domain}")
            elif compatibility_score > 0.4:
                # Medium compatibility - partial integration
                enhanced_caps = self.enhance_capabilities_partially(capabilities)
                integration_result['adaptation_decisions'].append(f"Partial integration for {domain}")
            else:
                # Low compatibility - minimal integration
                enhanced_caps = self.enhance_capabilities_minimally(capabilities)
                integration_result['adaptation_decisions'].append(f"Minimal integration for {domain}")
            
            integrated_capabilities.extend(enhanced_caps)
        
        # Calculate synergy score
        integration_result['synergy_score'] = self.calculate_adaptive_synergy(integrated_capabilities)
        integration_result['enhanced_capabilities'] = [cap.capability_name for cap in integrated_capabilities]
        
        return integration_result
    
    async def ensemble_integration(
        self, 
        domain_capabilities: Dict[str, List[AgentCapability]], 
        target_capabilities: List[str]
    ) -> Dict[str, Any]:
        """Ensemble integration strategy"""
        
        integration_result = {
            'strategy': 'ensemble',
            'synergy_score': 0.0,
            'enhanced_capabilities': [],
            'ensemble_weights': {}
        }
        
        # Create ensemble of all capabilities
        all_capabilities = []
        
        for domain, capabilities in domain_capabilities.items():
            # Calculate domain weight based on capability strength
            domain_weight = self.calculate_domain_weight(capabilities)
            integration_result['ensemble_weights'][domain] = domain_weight
            
            # Weight capabilities
            weighted_caps = self.weight_capabilities(capabilities, domain_weight)
            all_capabilities.extend(weighted_caps)
        
        # Calculate ensemble synergy
        integration_result['synergy_score'] = self.calculate_ensemble_synergy(all_capabilities)
        integration_result['enhanced_capabilities'] = [cap.capability_name for cap in all_capabilities]
        
        return integration_result
    
    async def create_capability_fusion_model(
        self, 
        session: Session,
        agent_id: str,
        domain_capabilities: Dict[str, List[AgentCapability]],
        integration_strategy: str
    ) -> FusionModel:
        """Create fusion model for integrated capabilities"""
        
        fusion_id = f"fusion_{uuid4().hex[:8]}"
        
        # Extract base models from capabilities
        base_models = []
        input_modalities = []
        
        for domain, capabilities in domain_capabilities.items():
            for cap in capabilities:
                base_models.append(cap.capability_id)
                input_modalities.append(cap.domain_area)
        
        # Remove duplicates
        base_models = list(set(base_models))
        input_modalities = list(set(input_modalities))
        
        fusion_model = FusionModel(
            fusion_id=fusion_id,
            model_name=f"capability_fusion_{agent_id}",
            fusion_type="cross_domain",
            base_models=base_models,
            input_modalities=input_modalities,
            fusion_strategy=integration_strategy,
            status="ready"
        )
        
        session.add(fusion_model)
        session.commit()
        session.refresh(fusion_model)
        
        return fusion_model
    
    # Helper methods for integration strategies
    def order_domains_by_strength(self, domain_capabilities: Dict[str, List[AgentCapability]]) -> List[str]:
        """Order domains by capability strength"""
        
        domain_strengths = {}
        
        for domain, capabilities in domain_capabilities.items():
            avg_strength = np.mean([cap.skill_level for cap in capabilities])
            domain_strengths[domain] = avg_strength
        
        return sorted(domain_strengths.keys(), key=lambda x: domain_strengths[x], reverse=True)
    
    def enhance_capabilities_sequentially(self, capabilities: List[AgentCapability], previous_capabilities: List[AgentCapability]) -> List[AgentCapability]:
        """Enhance capabilities sequentially"""
        
        enhanced = []
        
        for cap in capabilities:
            # Boost capability based on previous capabilities
            boost_factor = 1.0 + (len(previous_capabilities) * 0.05)
            
            enhanced_cap = AgentCapability(
                capability_id=cap.capability_id,
                agent_id=cap.agent_id,
                capability_name=cap.capability_name,
                capability_type=cap.capability_type,
                domain_area=cap.domain_area,
                skill_level=min(10.0, cap.skill_level * boost_factor),
                proficiency_score=min(1.0, cap.proficiency_score * boost_factor)
            )
            
            enhanced.append(enhanced_cap)
        
        return enhanced
    
    def enhance_capabilities_in_parallel(self, capabilities: List[AgentCapability]) -> List[AgentCapability]:
        """Enhance capabilities in parallel"""
        
        enhanced = []
        
        for cap in capabilities:
            # Parallel enhancement (moderate boost)
            boost_factor = 1.1
            
            enhanced_cap = AgentCapability(
                capability_id=cap.capability_id,
                agent_id=cap.agent_id,
                capability_name=cap.capability_name,
                capability_type=cap.capability_type,
                domain_area=cap.domain_area,
                skill_level=min(10.0, cap.skill_level * boost_factor),
                proficiency_score=min(1.0, cap.proficiency_score * boost_factor)
            )
            
            enhanced.append(enhanced_cap)
        
        return enhanced
    
    def enhance_capabilities_hierarchically(self, capabilities: List[AgentCapability]) -> List[AgentCapability]:
        """Enhance capabilities hierarchically"""
        
        enhanced = []
        
        for cap in capabilities:
            # Hierarchical enhancement based on capability level
            if cap.skill_level > 7.0:
                boost_factor = 1.2  # High-level capabilities get more boost
            elif cap.skill_level > 4.0:
                boost_factor = 1.1  # Mid-level capabilities get moderate boost
            else:
                boost_factor = 1.05  # Low-level capabilities get small boost
            
            enhanced_cap = AgentCapability(
                capability_id=cap.capability_id,
                agent_id=cap.agent_id,
                capability_name=cap.capability_name,
                capability_type=cap.capability_type,
                domain_area=cap.domain_area,
                skill_level=min(10.0, cap.skill_level * boost_factor),
                proficiency_score=min(1.0, cap.proficiency_score * boost_factor)
            )
            
            enhanced.append(enhanced_cap)
        
        return enhanced
    
    def enhance_capabilities_fully(self, capabilities: List[AgentCapability]) -> List[AgentCapability]:
        """Full enhancement"""
        
        enhanced = []
        
        for cap in capabilities:
            boost_factor = 1.25
            
            enhanced_cap = AgentCapability(
                capability_id=cap.capability_id,
                agent_id=cap.agent_id,
                capability_name=cap.capability_name,
                capability_type=cap.capability_type,
                domain_area=cap.domain_area,
                skill_level=min(10.0, cap.skill_level * boost_factor),
                proficiency_score=min(1.0, cap.proficiency_score * boost_factor)
            )
            
            enhanced.append(enhanced_cap)
        
        return enhanced
    
    def enhance_capabilities_partially(self, capabilities: List[AgentCapability]) -> List[AgentCapability]:
        """Partial enhancement"""
        
        enhanced = []
        
        for cap in capabilities:
            boost_factor = 1.1
            
            enhanced_cap = AgentCapability(
                capability_id=cap.capability_id,
                agent_id=cap.agent_id,
                capability_name=cap.capability_name,
                capability_type=cap.capability_type,
                domain_area=cap.domain_area,
                skill_level=min(10.0, cap.skill_level * boost_factor),
                proficiency_score=min(1.0, cap.proficiency_score * boost_factor)
            )
            
            enhanced.append(enhanced_cap)
        
        return enhanced
    
    def enhance_capabilities_minimally(self, capabilities: List[AgentCapability]) -> List[AgentCapability]:
        """Minimal enhancement"""
        
        enhanced = []
        
        for cap in capabilities:
            boost_factor = 1.02
            
            enhanced_cap = AgentCapability(
                capability_id=cap.capability_id,
                agent_id=cap.agent_id,
                capability_name=cap.capability_name,
                capability_type=cap.capability_type,
                domain_area=cap.domain_area,
                skill_level=min(10.0, cap.skill_level * boost_factor),
                proficiency_score=min(1.0, cap.proficiency_score * boost_factor)
            )
            
            enhanced.append(enhanced_cap)
        
        return enhanced
    
    def weight_capabilities(self, capabilities: List[AgentCapability], weight: float) -> List[AgentCapability]:
        """Weight capabilities"""
        
        weighted = []
        
        for cap in capabilities:
            weighted_cap = AgentCapability(
                capability_id=cap.capability_id,
                agent_id=cap.agent_id,
                capability_name=cap.capability_name,
                capability_type=cap.capability_type,
                domain_area=cap.domain_area,
                skill_level=min(10.0, cap.skill_level * weight),
                proficiency_score=min(1.0, cap.proficiency_score * weight)
            )
            
            weighted.append(weighted_cap)
        
        return weighted
    
    # Synergy calculation methods
    def calculate_sequential_synergy(self, capabilities: List[AgentCapability]) -> float:
        """Calculate sequential synergy"""
        
        if len(capabilities) < 2:
            return 0.0
        
        # Sequential synergy based on order and complementarity
        synergy = 0.0
        
        for i in range(len(capabilities) - 1):
            cap1 = capabilities[i]
            cap2 = capabilities[i + 1]
            
            # Complementarity bonus
            if cap1.domain_area != cap2.domain_area:
                synergy += 0.2
            else:
                synergy += 0.1
            
            # Skill level bonus
            avg_skill = (cap1.skill_level + cap2.skill_level) / 2
            synergy += avg_skill / 50.0
        
        return min(1.0, synergy / len(capabilities))
    
    def calculate_parallel_synergy(self, capabilities: List[AgentCapability]) -> float:
        """Calculate parallel synergy"""
        
        if len(capabilities) < 2:
            return 0.0
        
        # Parallel synergy based on diversity and strength
        domains = set(cap.domain_area for cap in capabilities)
        avg_skill = np.mean([cap.skill_level for cap in capabilities])
        
        diversity_bonus = len(domains) / len(capabilities)
        strength_bonus = avg_skill / 10.0
        
        return min(1.0, (diversity_bonus + strength_bonus) / 2)
    
    def calculate_hierarchical_synergy(self, capabilities: List[AgentCapability]) -> float:
        """Calculate hierarchical synergy"""
        
        if len(capabilities) < 2:
            return 0.0
        
        # Hierarchical synergy based on structure and complementarity
        high_level_caps = [cap for cap in capabilities if cap.skill_level > 7.0]
        low_level_caps = [cap for cap in capabilities if cap.skill_level <= 7.0]
        
        structure_bonus = 0.5  # Base bonus for hierarchical structure
        
        if high_level_caps and low_level_caps:
            structure_bonus += 0.3  # Bonus for having both levels
        
        avg_skill = np.mean([cap.skill_level for cap in capabilities])
        skill_bonus = avg_skill / 10.0
        
        return min(1.0, structure_bonus + skill_bonus)
    
    def calculate_adaptive_synergy(self, capabilities: List[AgentCapability]) -> float:
        """Calculate adaptive synergy"""
        
        if len(capabilities) < 2:
            return 0.0
        
        # Adaptive synergy based on compatibility and optimization
        avg_skill = np.mean([cap.skill_level for cap in capabilities])
        domains = set(cap.domain_area for cap in capabilities)
        
        compatibility_bonus = len(domains) / len(capabilities)
        optimization_bonus = avg_skill / 10.0
        
        return min(1.0, (compatibility_bonus + optimization_bonus) / 2)
    
    def calculate_ensemble_synergy(self, capabilities: List[AgentCapability]) -> float:
        """Calculate ensemble synergy"""
        
        if len(capabilities) < 2:
            return 0.0
        
        # Ensemble synergy based on collective strength and diversity
        total_strength = sum(cap.skill_level for cap in capabilities)
        max_possible_strength = len(capabilities) * 10.0
        
        strength_ratio = total_strength / max_possible_strength
        diversity_ratio = len(set(cap.domain_area for cap in capabilities)) / len(capabilities)
        
        return min(1.0, (strength_ratio + diversity_ratio) / 2)
    
    # Additional helper methods
    def analyze_capability_compatibility(self, domain_capabilities: Dict[str, List[AgentCapability]]) -> Dict[str, float]:
        """Analyze capability compatibility between domains"""
        
        compatibility_matrix = {}
        domains = list(domain_capabilities.keys())
        
        for domain in domains:
            compatibility_score = 0.0
            
            # Calculate compatibility with other domains
            for other_domain in domains:
                if domain != other_domain:
                    # Simplified compatibility calculation
                    domain_caps = domain_capabilities[domain]
                    other_caps = domain_capabilities[other_domain]
                    
                    # Compatibility based on skill levels and domain types
                    avg_skill_domain = np.mean([cap.skill_level for cap in domain_caps])
                    avg_skill_other = np.mean([cap.skill_level for cap in other_caps])
                    
                    # Domain compatibility (simplified)
                    domain_compatibility = self.get_domain_compatibility(domain, other_domain)
                    
                    compatibility_score += (avg_skill_domain + avg_skill_other) / 20.0 * domain_compatibility
            
            # Average compatibility
            if len(domains) > 1:
                compatibility_matrix[domain] = compatibility_score / (len(domains) - 1)
            else:
                compatibility_matrix[domain] = 0.5
        
        return compatibility_matrix
    
    def get_domain_compatibility(self, domain1: str, domain2: str) -> float:
        """Get compatibility between two domains"""
        
        # Simplified domain compatibility matrix
        compatibility_matrix = {
            ('cognitive', 'analytical'): 0.9,
            ('cognitive', 'technical'): 0.8,
            ('cognitive', 'creative'): 0.7,
            ('cognitive', 'social'): 0.8,
            ('analytical', 'technical'): 0.9,
            ('analytical', 'creative'): 0.6,
            ('analytical', 'social'): 0.7,
            ('technical', 'creative'): 0.7,
            ('technical', 'social'): 0.6,
            ('creative', 'social'): 0.8
        }
        
        key = tuple(sorted([domain1, domain2]))
        return compatibility_matrix.get(key, 0.5)
    
    def calculate_domain_weight(self, capabilities: List[AgentCapability]) -> float:
        """Calculate weight for domain based on capability strength"""
        
        if not capabilities:
            return 0.0
        
        avg_skill = np.mean([cap.skill_level for cap in capabilities])
        avg_proficiency = np.mean([cap.proficiency_score for cap in capabilities])
        
        return (avg_skill / 10.0 + avg_proficiency) / 2
    
    def build_capability_hierarchy(self, domain_capabilities: Dict[str, List[AgentCapability]]) -> List[List[AgentCapability]]:
        """Build capability hierarchy"""
        
        hierarchy = []
        
        # Level 1: High-level capabilities (skill > 7)
        level1 = []
        # Level 2: Mid-level capabilities (skill > 4)
        level2 = []
        # Level 3: Low-level capabilities (skill <= 4)
        level3 = []
        
        for capabilities in domain_capabilities.values():
            for cap in capabilities:
                if cap.skill_level > 7.0:
                    level1.append(cap)
                elif cap.skill_level > 4.0:
                    level2.append(cap)
                else:
                    level3.append(cap)
        
        if level1:
            hierarchy.append(level1)
        if level2:
            hierarchy.append(level2)
        if level3:
            hierarchy.append(level3)
        
        return hierarchy
