"""Sync utilities for AITBC.

Provides peer capability tracking, parallel block fetching from multiple
peers, and block-to-block state diff computation for delta sync.
"""

from __future__ import annotations

from .parallel_fetcher import NoPeersAvailableError, ParallelBlockFetcher
from .peer_capability import PeerCapability, PeerCapabilityTracker
from .state_diff import (
    AccountChange,
    StateDiff,
    apply_state_diff,
    compute_state_diff,
    decode_state_diff,
    encode_state_diff,
)

__all__ = [
    "AccountChange",
    "NoPeersAvailableError",
    "ParallelBlockFetcher",
    "PeerCapability",
    "PeerCapabilityTracker",
    "StateDiff",
    "apply_state_diff",
    "compute_state_diff",
    "decode_state_diff",
    "encode_state_diff",
]
