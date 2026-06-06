"""
SAC Agent implementation
"""

import torch
import torch.nn as nn


class SACAgent(nn.Module):
    """Soft Actor-Critic Agent"""

    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 256):
        super().__init__()
        self.actor_mean = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim),
        )
        self.actor_log_std = nn.Parameter(torch.zeros(1, action_dim))

        self.qf1 = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

        self.qf2 = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, state):  # type: ignore[no-untyped-def]
        mean = self.actor_mean(state)
        std = torch.exp(self.actor_log_std)
        return mean, std
