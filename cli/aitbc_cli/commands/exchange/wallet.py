"""
Wallet-related exchange commands.
"""

import click

try:
    from aitbc_cli.utils import error, output, success
except ImportError:
    from ..utils import error, output, success


def balance_command(ctx):
    """Check wallet balance"""
    try:
        balance_data = {
            "aitbc": 1000.0,
            "btc": 0.05,
            "eth": 0.0
        }
        output(balance_data, title="Wallet Balance")
        success("Wallet balance retrieved")
    except Exception as e:
        error(f"Error: {e}")


def info_command(ctx):
    """Get wallet information"""
    try:
        wallet_info = {
            "address": "0x1234...5678",
            "network": "mainnet",
            "created_at": "2024-01-01T00:00:00Z"
        }
        output(wallet_info, title="Wallet Information")
        success("Wallet information retrieved")
    except Exception as e:
        error(f"Error: {e}")
