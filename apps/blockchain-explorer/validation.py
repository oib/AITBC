"""Validation patterns and functions for user inputs to prevent SSRF."""

import re

from fastapi import HTTPException

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


# PI-EX-001: every client-supplied page size must be bounded before it
# reaches a SQL LIMIT/OFFSET or an upstream RPC parameter. SQLite treats
# LIMIT -1 as "no limit" and a huge LIMIT turns a bounded query into a
# full-table dump plus per-row fan-out; an unbounded OFFSET makes SQLite
# scan and discard arbitrarily deep. Limits clamp into range (a too-large
# request still gets a useful page); offsets outside the window reject —
# silently clamping a deep offset would return the wrong page.
MAX_PAGE_LIMIT = 200
MAX_PAGE_OFFSET = 10_000
MAX_ANALYTICS_DAYS = 365


def clamp_page_limit(limit: int) -> int:
    """Bound a client-supplied page size to ``1..MAX_PAGE_LIMIT``."""
    return max(1, min(int(limit), MAX_PAGE_LIMIT))


def check_page_offset(offset: int) -> int:
    """Reject an out-of-range page offset; return it unchanged when valid."""
    if offset < 0 or offset > MAX_PAGE_OFFSET:
        raise HTTPException(status_code=400, detail=f"offset must be 0..{MAX_PAGE_OFFSET}")
    return offset


def clamp_analytics_days(days: int) -> int:
    """Bound the activity-timeline window to ``1..MAX_ANALYTICS_DAYS``."""
    return max(1, min(int(days), MAX_ANALYTICS_DAYS))
