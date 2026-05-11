"""
CLI utility functions for output formatting and error handling
"""

from click import echo, secho

# Import new utility modules
from .wallet import decrypt_private_key
from .blockchain import get_chain_info, get_network_status, get_blockchain_analytics


def output(message: str, **kwargs):
    """Print a regular output message"""
    echo(message, **kwargs)


def error(message: str, **kwargs):
    """Print an error message in red"""
    secho(message, fg="red", **kwargs)


def success(message: str, **kwargs):
    """Print a success message in green"""
    secho(message, fg="green", **kwargs)


def info(message: str, **kwargs):
    """Print an info message in blue"""
    secho(message, fg="blue", **kwargs)


def warning(message: str, **kwargs):
    """Print a warning message in yellow"""
    secho(message, fg="yellow", **kwargs)


__all__ = [
    'output',
    'error',
    'success',
    'info',
    'warning',
    'decrypt_private_key',
    'get_chain_info',
    'get_network_status',
    'get_blockchain_analytics',
]
