"""HTLC (Hashed Timelock Contract) utilities for atomic settlement (v0.9.0 §A2).

Provides secret generation, hashlock computation, timelock calculation,
and HTLC state machine management for cross-chain atomic settlement.

The HTLC protocol works as follows:
1. Buyer generates a random secret and computes its SHA256 hash (hashlock)
2. Buyer locks funds on source chain with hashlock + source_timelock
3. Seller locks funds on dest chain with same hashlock + dest_timelock
   (dest_timelock < source_timelock to give buyer time after secret reveal)
4. Seller reveals secret on dest chain to claim funds (before dest_timelock)
5. Buyer observes revealed secret, uses it to claim on source chain
   (before source_timelock)
6. If either timelock expires, funds are refunded

The timelock ordering is critical:
- dest_timelock must expire BEFORE source_timelock
- This ensures: if seller reveals secret, buyer has time to claim on source
- If seller doesn't reveal, both chains refund after their respective timelocks
"""

from __future__ import annotations

import hashlib
import secrets

from .types import HTLCState


def generate_secret() -> str:
    """Generate a cryptographically random 32-byte secret.

    Returns a hex-encoded string (64 characters). The secret should be
    kept private by the buyer until it is revealed on the destination
    chain to claim funds.

    Uses ``secrets.token_hex(32)`` which is cryptographically secure.
    """
    return secrets.token_hex(32)


def compute_hashlock(secret: str) -> str:
    """Compute the SHA256 hash of a secret (the hashlock).

    The hashlock is published on-chain when initiating the HTLC. The
    secret is revealed later to claim funds. This matches the
    ``CrossChainAtomicSwap.sol`` contract which uses ``sha256(secret)``.

    Args:
        secret: Hex-encoded secret string (e.g., from ``generate_secret()``)

    Returns:
        Hex-encoded SHA256 hash (64 characters)
    """
    return hashlib.sha256(secret.encode()).hexdigest()


def verify_secret(secret: str, hashlock: str) -> bool:
    """Verify that a secret matches a hashlock.

    Used to validate that a revealed secret is correct before attempting
    to claim funds from an HTLC contract.

    Args:
        secret: The revealed secret (hex string)
        hashlock: The expected hashlock (hex string)

    Returns:
        True if SHA256(secret) == hashlock, False otherwise
    """
    return compute_hashlock(secret) == hashlock


def calculate_source_timelock(
    current_block_height: int,
    timeout_seconds: int,
    block_time_seconds: int,
    margin_blocks: int = 10,
) -> int:
    """Calculate the source chain timelock (block height).

    The source timelock must be LATER than the destination timelock to
    give the buyer time to claim funds on the source chain after the
    seller reveals the secret on the destination chain.

    Formula:
        source_timelock = current_height + (timeout_seconds / block_time_seconds) + margin_blocks

    Args:
        current_block_height: Current block height on source chain
        timeout_seconds: Desired timeout duration in seconds
        block_time_seconds: Block time on source chain (seconds per block)
        margin_blocks: Extra blocks for safety margin

    Returns:
        Source chain timelock as a block height
    """
    if block_time_seconds <= 0:
        raise ValueError("block_time_seconds must be positive")
    timeout_blocks = timeout_seconds // block_time_seconds
    return current_block_height + timeout_blocks + margin_blocks


def calculate_dest_timelock(
    source_timelock: int,
    source_block_time: int,
    dest_block_time: int,
    margin_blocks: int = 20,
) -> int:
    """Calculate the destination chain timelock (block height).

    The dest timelock must be EARLIER than the source timelock (when
    converted to the same time base) so that:
    1. Seller must reveal secret on dest chain before dest timelock
    2. Buyer has time to use the revealed secret on source chain before
       source timelock expires

    The conversion accounts for different block times between chains.
    The margin_blocks provides additional safety to ensure the dest
    timelock expires well before the source timelock.

    Formula:
        dest_timelock = source_timelock * (dest_block_time / source_block_time) - margin_blocks

    Args:
        source_timelock: Source chain timelock (block height)
        source_block_time: Block time on source chain (seconds per block)
        dest_block_time: Block time on dest chain (seconds per block)
        margin_blocks: Extra blocks subtracted for safety margin

    Returns:
        Destination chain timelock as a block height
    """
    if source_block_time <= 0:
        raise ValueError("source_block_time must be positive")
    if dest_block_time <= 0:
        raise ValueError("dest_block_time must be positive")
    # Convert source timelock to seconds, then to dest chain blocks
    source_timeout_seconds = source_timelock * source_block_time
    dest_timeout_blocks = source_timeout_seconds // dest_block_time
    result = dest_timeout_blocks - margin_blocks
    return max(result, 1)  # ensure at least 1 block


def validate_timelocks(
    source_timelock: int,
    dest_timelock: int,
    source_current_height: int,
    dest_current_height: int,
    source_block_time: int = 5,
    dest_block_time: int = 5,
    min_margin_seconds: int = 300,
) -> list[str]:
    """Validate that timelocks are safe for atomic settlement.

    Returns a list of error strings. An empty list means the timelocks
    are valid.

    Checks:
    1. Source timelock is in the future (above current height)
    2. Dest timelock is in the future (above current height)
    3. Dest timelock expires before source timelock (when converted to
       same time base in seconds)
    4. Sufficient margin between dest and source timelock expiry
       (at least ``min_margin_seconds``)

    Args:
        source_timelock: Source chain timelock (block height)
        dest_timelock: Dest chain timelock (block height)
        source_current_height: Current block height on source chain
        dest_current_height: Current block height on dest chain
        source_block_time: Block time on source chain (seconds per block)
        dest_block_time: Block time on dest chain (seconds per block)
        min_margin_seconds: Minimum required margin between dest and
            source timelock expiry in seconds

    Returns:
        List of error strings (empty if valid)
    """
    errors: list[str] = []

    # Check 1: Source timelock is in the future
    if source_timelock <= source_current_height:
        errors.append(f"Source timelock {source_timelock} must be above current height {source_current_height}")

    # Check 2: Dest timelock is in the future
    if dest_timelock <= dest_current_height:
        errors.append(f"Dest timelock {dest_timelock} must be above current height {dest_current_height}")

    # Convert both timelocks to absolute time (seconds from now)
    source_remaining_blocks = source_timelock - source_current_height
    dest_remaining_blocks = dest_timelock - dest_current_height
    source_expiry_seconds = source_remaining_blocks * source_block_time
    dest_expiry_seconds = dest_remaining_blocks * dest_block_time

    # Check 3: Dest timelock expires before source timelock
    if dest_expiry_seconds >= source_expiry_seconds:
        errors.append(
            f"Dest timelock expires in {dest_expiry_seconds}s but must "
            f"expire before source timelock ({source_expiry_seconds}s)"
        )

    # Check 4: Sufficient margin between dest and source expiry
    margin_seconds = source_expiry_seconds - dest_expiry_seconds
    if margin_seconds < min_margin_seconds:
        errors.append(
            f"Margin between dest and source timelock expiry is {margin_seconds}s but must be at least {min_margin_seconds}s"
        )

    return errors


class HTLCStateMachine:
    """State machine for HTLC lifecycle management.

    Tracks valid state transitions for an HTLC on a single chain:

    .. code-block:: text

        created → funded → completed (terminal)
                ↘          ↘ refunded (terminal)
                 expired → refunded

    The state machine ensures that HTLCs follow the correct lifecycle
    and prevents invalid transitions (e.g., from completed to refunded).
    """

    def __init__(self) -> None:
        self._transitions: dict[HTLCState, set[HTLCState]] = {
            HTLCState.CREATED: {HTLCState.FUNDED, HTLCState.EXPIRED},
            HTLCState.FUNDED: {HTLCState.COMPLETED, HTLCState.REFUNDED, HTLCState.EXPIRED},
            HTLCState.COMPLETED: set(),  # terminal
            HTLCState.REFUNDED: set(),  # terminal
            HTLCState.EXPIRED: {HTLCState.REFUNDED},
        }

    def can_transition(self, from_state: HTLCState, to_state: HTLCState) -> bool:
        """Check if a transition between two states is valid."""
        allowed = self._transitions.get(from_state, set())
        return to_state in allowed

    def transition(self, from_state: HTLCState, to_state: HTLCState) -> HTLCState:
        """Execute a state transition.

        Raises:
            ValueError: If the transition is not valid
        """
        if not self.can_transition(from_state, to_state):
            raise ValueError(f"Invalid HTLC state transition: {from_state} → {to_state}")
        return to_state

    def is_terminal(self, state: HTLCState) -> bool:
        """Check if a state is terminal (no further transitions possible)."""
        return len(self._transitions.get(state, set())) == 0
