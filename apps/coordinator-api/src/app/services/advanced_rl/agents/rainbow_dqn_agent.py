"""
Rainbow DQN Agent implementation
"""

import torch
import torch.nn as nn


class RainbowDQNAgent(nn.Module):
    """Rainbow DQN Agent with multiple improvements"""

    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 512, num_atoms: int = 51):
        super().__init__()
        self.num_atoms = num_atoms
        self.action_dim = action_dim

        # Feature extractor
        self.feature_layer = nn.Sequential(
            nn.Linear(state_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim), nn.ReLU()
        )

        # Dueling network architecture
        self.value_stream = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2), nn.ReLU(), nn.Linear(hidden_dim // 2, num_atoms)
        )

        self.advantage_stream = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2), nn.ReLU(), nn.Linear(hidden_dim // 2, action_dim * num_atoms)
        )

    def forward(self, state):
        features = self.feature_layer(state)
        values = self.value_stream(features)
        advantages = self.advantage_stream(features)

        # Reshape for distributional RL
        advantages = advantages.view(-1, self.action_dim, self.num_atoms)
        values = values.view(-1, 1, self.num_atoms)

        # Dueling architecture
        q_atoms = values + advantages - advantages.mean(dim=1, keepdim=True)
        return q_atoms
