"""
AITBC Training Environment Setup Module

Provides Python-based training environment setup as an alternative to shell scripts.
Uses existing AITBC patterns and integrates with pytest fixtures.
"""

from .environment import TrainingEnvironment
from .exceptions import FundingError, MessagingError, TrainingSetupError

__all__ = [
    "TrainingEnvironment",
    "TrainingSetupError",
    "FundingError",
    "MessagingError",
]
