"""
Custom exceptions for training environment setup.
"""


class TrainingSetupError(Exception):
    """Base exception for training setup errors."""
    pass


class FundingError(TrainingSetupError):
    """Exception raised when account funding fails."""
    pass


class MessagingError(TrainingSetupError):
    """Exception raised when messaging configuration fails."""
    pass


class FaucetError(TrainingSetupError):
    """Exception raised when faucet setup fails."""
    pass


class PrerequisitesError(TrainingSetupError):
    """Exception raised when prerequisites are not met."""
    pass
