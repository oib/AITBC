"""Validation patterns and functions for user inputs to prevent SSRF."""

import re

# Validation patterns for user inputs to prevent SSRF
TX_HASH_PATTERN = re.compile(r"^(0x)?[a-fA-F0-9]{64}$")  # 64-character hex string, optional 0x prefix
CHAIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,100}$")  # Chain ID pattern (allows dots)


def validate_tx_hash(tx_hash: str) -> bool:
    """Validate transaction hash to prevent SSRF"""
    if not tx_hash:
        return False
    # Check for path traversal or URL manipulation
    if any(char in tx_hash for char in ["/", "\\", "..", "\n", "\r", "\t", "?", "&"]):
        return False
    # Validate against hash pattern (allows optional 0x prefix)
    return bool(TX_HASH_PATTERN.match(tx_hash))


def validate_chain_id(chain_id: str) -> bool:
    """Validate chain ID to prevent SSRF"""
    if not chain_id:
        return False
    # Check for path traversal or URL manipulation
    if any(char in chain_id for char in ["/", "\\", "..", "\n", "\r", "\t", "?", "&"]):
        return False
    # Validate against chain ID pattern
    return bool(CHAIN_ID_PATTERN.match(chain_id))
