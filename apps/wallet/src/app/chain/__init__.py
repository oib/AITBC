"""
Multi-Chain Support Module for Wallet Daemon

This module provides multi-chain capabilities for the wallet daemon,
including chain management, chain-specific storage, and chain-aware
wallet operations.
"""

from .chain_aware_wallet_service import ChainAwareWalletService
from .manager import ChainConfig, ChainManager, ChainStatus, chain_manager
from .multichain_ledger import ChainLedgerRecord, ChainWalletMetadata, MultiChainLedgerAdapter

__all__ = [
    "ChainManager",
    "ChainConfig",
    "ChainStatus",
    "chain_manager",
    "MultiChainLedgerAdapter",
    "ChainLedgerRecord",
    "ChainWalletMetadata",
    "ChainAwareWalletService",
]
