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
import hmac
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
    derived = compute_hashlock(secret)
    if len(derived) != len(hashlock):
        return False
    return hmac.compare_digest(derived, hashlock)


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
    source_current_height: int,
    source_block_time: int,
    dest_current_height: int,
    dest_block_time: int,
    margin_seconds: int = 300,
) -> int:
    """Calculate the destination chain timelock (block height).

    The dest timelock must expire EARLIER than the source timelock in
    wall-clock terms, so that:
    1. The seller must reveal the secret on the dest chain before dest_timelock
    2. The buyer still has ``margin_seconds`` to use the revealed secret on the
       source chain before source_timelock expires

    Block heights on two chains are independent quantities. A height on the
    source chain says nothing about what height the dest chain will be at
    when that moment arrives, so both current heights are required: the
    remaining *duration* is what converts between chains, not the height.

    Formula:
        source_remaining = (source_timelock - source_current_height) * source_block_time
        dest_remaining   = source_remaining - margin_seconds
        dest_timelock    = dest_current_height + dest_remaining // dest_block_time

    ``dest_remaining`` is floored into whole dest blocks, which can only move
    the dest timelock earlier -- so the realised margin is always at least
    ``margin_seconds``, never less.

    Args:
        source_timelock: Source chain timelock (absolute block height)
        source_current_height: Current block height on the source chain
        source_block_time: Block time on source chain (seconds per block)
        dest_current_height: Current block height on the dest chain
        dest_block_time: Block time on dest chain (seconds per block)
        margin_seconds: Wall-clock safety margin between dest and source
            expiry. Defaults to 300, matching ``validate_timelocks``.

    Returns:
        Destination chain timelock as an absolute block height

    Raises:
        ValueError: If a block time is not positive, if the source timelock is
            not in the future, or if the source window is too short to leave
            ``margin_seconds`` plus at least one dest block.

    Note:
        This previously took ``(source_timelock, source_block_time,
        dest_block_time, margin_blocks)`` and computed
        ``source_timelock * source_block_time // dest_block_time``, treating an
        absolute height as a duration and never consulting the dest chain. The
        same inputs produced a timelock weeks away or already expired depending
        on the dest height it never saw. The signature changed rather than
        gaining optional arguments because there is no correct value to default
        the heights to, and a silently-wrong swap is worse than a broken build.
    """
    if source_block_time <= 0:
        raise ValueError("source_block_time must be positive")
    if dest_block_time <= 0:
        raise ValueError("dest_block_time must be positive")
    if margin_seconds < 0:
        raise ValueError("margin_seconds must not be negative")

    source_remaining_blocks = source_timelock - source_current_height
    if source_remaining_blocks <= 0:
        raise ValueError(f"source_timelock {source_timelock} is not above source_current_height {source_current_height}")

    source_remaining_seconds = source_remaining_blocks * source_block_time
    dest_remaining_seconds = source_remaining_seconds - margin_seconds
    dest_remaining_blocks = dest_remaining_seconds // dest_block_time

    if dest_remaining_blocks < 1:
        raise ValueError(
            f"source window of {source_remaining_seconds}s is too short to leave "
            f"a {margin_seconds}s margin plus one {dest_block_time}s dest block"
        )

    return dest_current_height + dest_remaining_blocks


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
