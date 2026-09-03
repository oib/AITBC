"""Python-native HTLC contract implementation (v0.9.0 B4).

Mirrors the logic of ``CrossChainAtomicSwap.sol``:

    initiate_swap(swap_id, participant, token, amount, hashlock, timelock)
    complete_swap(swap_id, secret)
    refund_swap(swap_id)

The Solidity contract locks funds in an EVM mapping; this implementation
locks funds by queueing a transfer from the initiator to a keyless escrow
address. On completion the escrow pays the participant; on refund it pays the
initiator back.

Every one of those movements is a mempool transaction settled during block
processing -- this module never writes an ``Account`` balance itself. Balances
are covered by the block header's ``state_root``, so a mutation applied here
would make the proposer's computed root disagree with the header it signed and
stall block production.

All state transitions are persisted via the ``HTLCSwapRecord`` SQLModel so
swap state survives node restarts.
"""

from __future__ import annotations

import hashlib
import time
from enum import StrEnum

from sqlmodel import Session

from aitbc.utils.chain_config import ChainConfigParser

from ..base_models import Account, HTLCSwapState
from ..config import settings
from ..logger import get_logger
from ..protocol_escrow import confirmed_lock_total, htlc_escrow_address, queue_protocol_transfer

logger = get_logger(__name__)


def _get_chain_block_time_seconds(chain_id: str) -> int:
    """Return the configured block time for a chain, falling back to the global default."""
    config_str = settings.chain_configs.get(chain_id, "")
    if config_str:
        parsed = ChainConfigParser.parse(config_str)
        block_time = parsed.get("block_time_seconds")
        if isinstance(block_time, int) and block_time > 0:
            return block_time
    return settings.block_time_seconds


# The HTLC contract's escrow account. In an EVM chain this would be the
# deployed contract address; here it is a keyless address derived from a fixed
# label, holding locked funds until swap completion or refund. Keyless is the
# security barrier: no private key exists for it, so no signature can ever
# recover to it and only this module can move its funds.
#
# coordinator-api defines a same-named constant of its own. That one is a
# descriptive string in swap metadata and is deliberately not kept in sync.
HTLC_CONTRACT_ADDRESS = htlc_escrow_address()


class SwapStatus(StrEnum):
    INVALID = "invalid"
    OPEN = "open"
    COMPLETED = "completed"
    REFUNDED = "refunded"


class HTLCSwapRecord:
    """In-memory representation of a swap (persisted via DB).

    Mirrors the Solidity ``Swap`` struct:

        initiator, participant, token, amount, hashlock, timelock, status
    """

    def __init__(
        self,
        swap_id: str,
        initiator: str,
        participant: str,
        token: str,
        amount: int,
        hashlock: str,
        timelock: int,
        status: SwapStatus = SwapStatus.OPEN,
        secret: str = "",
        created_at: float = 0.0,
        completed_at: float = 0.0,
        refunded_at: float = 0.0,
    ) -> None:
        self.swap_id = swap_id
        self.initiator = initiator
        self.participant = participant
        self.token = token  # "native" or token address (address(0) in Solidity)
        self.amount = amount
        self.hashlock = hashlock
        self.timelock = timelock
        self.status = status
        self.secret = secret
        self.created_at = created_at
        self.completed_at = completed_at
        self.refunded_at = refunded_at


def _get_current_height(session: Session, chain_id: str) -> int:
    """Return the current head height for a chain from the database.

    Timelocks stored on a swap are absolute block heights. Comparing them
    against ``int(time.time() // block_time)`` -- the Unix epoch over the block
    time -- compares a height to a number in the hundreds of millions.

    That went unnoticed because the code that *produced* the timelocks used the
    same expression, so producer and checker were consistently wrong together
    and the swaps behaved plausibly. Once the producer reads real heights (see
    cross_chain/settlement.py), a checker still on epoch time treats every swap
    as expired.

    Raises:
        ValueError: If the chain has no blocks. Refusing is the only safe
            answer: treating "height unknown" as "not expired" would let a
            claim through after the refund window, and the reverse would strand
            funds.
    """
    from sqlalchemy import text
    from sqlmodel import select

    from ..base_models import Block

    stmt = select(Block).where(Block.chain_id == chain_id).order_by(text("height DESC")).limit(1)
    head = session.execute(stmt).scalars().first()
    if head is None:
        raise ValueError(f"cannot determine current height for chain {chain_id!r}: no blocks in database")
    return int(head.height)


def _compute_swap_id(
    initiator: str,
    participant: str,
    hashlock: str,
    timelock: int,
    amount: int,
) -> str:
    """Compute a deterministic swap ID (mirrors Solidity keccak256 pattern)."""
    data = f"{initiator}:{participant}:{hashlock}:{timelock}:{amount}".encode()
    return "0x" + hashlib.sha256(data).hexdigest()


def _require_balance(session: Session, chain_id: str, address: str, amount: int) -> None:
    """Reject early if ``address`` visibly cannot cover ``amount``.

    Advisory only. The authoritative check is in the block-time transfer, which
    re-reads the balance at execution; the initiator may spend elsewhere between
    here and inclusion, in which case the proposer drops the lock and the swap
    never becomes claimable (see ``_require_locked``).
    """
    account = session.get(Account, (chain_id, address))
    balance = account.balance if account is not None else 0
    if balance < amount:
        raise ValueError(f"Insufficient balance for {address}: has {balance}, needs {amount}")


def _require_locked(session: Session, chain_id: str, swap_state: HTLCSwapState) -> None:
    """Refuse to pay out of the escrow until this swap's lock is in a block.

    The escrow is shared across all swaps, so paying out against a lock that is
    still in the mempool -- or that the proposer dropped because the initiator
    had since spent the balance -- would take other swaps' principal.
    """
    funded = confirmed_lock_total(session, chain_id, "HTLC_LOCK", "swap_id", swap_state.swap_id)
    if funded < swap_state.amount:
        raise ValueError(
            f"Swap {swap_state.swap_id} lock is not confirmed on-chain "
            f"({funded} of {swap_state.amount} locked); retry once it is included in a block"
        )


class HTLCContract:
    """Python-native HTLC contract that manages swap state and fund movement.

    Each method operates within a DB session and atomically updates both the
    swap state and account balances. The contract address
    ``HTLC_CONTRACT_ADDRESS`` acts as the escrow holder for locked funds.

    Usage::

        htlc = HTLCContract(chain_id="ait-hub")
        swap = htlc.initiate_swap(
            initiator="0xalice",
            participant="0xbob",
            amount=36000000,  # 1 AIT in compute-units
            hashlock=secret_hash,
            timelock=block_height,
        )
        htlc.complete_swap(swap.swap_id, secret)   # releases to participant
        # or
        htlc.refund_swap(swap.swap_id)              # returns to initiator
    """

    def __init__(self, chain_id: str = "") -> None:
        self.chain_id = chain_id

    def initiate_swap(
        self,
        session: Session,
        initiator: str,
        participant: str,
        amount: int,
        hashlock: str,
        timelock: int,
        token: str = "native",
        swap_id: str | None = None,
    ) -> HTLCSwapRecord:
        """Initiate an atomic swap — lock funds in the contract escrow account.

        Mirrors ``CrossChainAtomicSwap.initiateSwap()``:
        - Validates swap doesn't already exist
        - Validates participant is not zero address
        - Validates timelock is in the future
        - Validates amount > 0
        - Transfers funds from initiator to contract escrow account
        - Records swap state as OPEN

        Args:
            session: Active DB session.
            initiator: Sender address (funds debited from here).
            participant: Recipient address (funds credited on completion).
            amount: Amount to lock (in compute-units).
            hashlock: SHA256 hash of the secret.
            timelock: Block height after which the swap can be refunded.
            token: "native" or token contract address.
            swap_id: Optional swap ID; auto-computed if not provided.

        Returns:
            HTLCSwapRecord with the swap details.

        Raises:
            ValueError: If validation fails or insufficient balance.
        """
        if not participant or participant == "0x0":
            raise ValueError("Invalid participant address")
        if timelock <= 0:
            raise ValueError("Timelock must be in the future")
        if amount <= 0:
            raise ValueError("Amount must be > 0")

        if swap_id is None:
            swap_id = _compute_swap_id(initiator, participant, hashlock, timelock, amount)

        # Check swap doesn't already exist (query HTLCSwapState from DB)
        existing = session.get(HTLCSwapState, swap_id)
        if existing is not None and existing.status != SwapStatus.INVALID.value:
            raise ValueError(f"Swap ID already exists: {swap_id}")

        # Queue the lock; it settles against balances during block processing.
        _require_balance(session, self.chain_id, initiator, amount)
        queue_protocol_transfer(
            sender=initiator,
            recipient=HTLC_CONTRACT_ADDRESS,
            amount=amount,
            chain_id=self.chain_id,
            tx_type="HTLC_LOCK",
            payload={"swap_id": swap_id},
        )

        # Persist swap state
        now = time.time()
        swap_state = HTLCSwapState(
            swap_id=swap_id,
            initiator=initiator,
            participant=participant,
            token=token,
            amount=amount,
            hashlock=hashlock,
            timelock=timelock,
            status=SwapStatus.OPEN.value,
            created_at=now,
        )
        session.add(swap_state)
        session.flush()

        logger.info(
            "HTLC swap initiated: swap_id=%s initiator=%s participant=%s amount=%d hashlock=%s timelock=%d",
            swap_id,
            initiator,
            participant,
            amount,
            hashlock,
            timelock,
        )

        return HTLCSwapRecord(
            swap_id=swap_id,
            initiator=initiator,
            participant=participant,
            token=token,
            amount=amount,
            hashlock=hashlock,
            timelock=timelock,
            status=SwapStatus.OPEN,
            created_at=now,
        )

    def complete_swap(self, session: Session, swap_id: str, secret: str) -> HTLCSwapRecord:
        """Complete a swap by revealing the secret — release funds to participant.

        Mirrors ``CrossChainAtomicSwap.completeSwap()``:
        - Validates swap is OPEN
        - Validates timelock hasn't expired
        - Validates SHA256(secret) == hashlock
        - Transfers funds from contract escrow to participant
        - Records swap state as COMPLETED

        Args:
            session: Active DB session.
            swap_id: The swap to complete.
            secret: The revealed secret (hex string).

        Returns:
            Updated HTLCSwapRecord.

        Raises:
            ValueError: If swap not found, not open, expired, or secret invalid.
        """
        swap_state = session.get(HTLCSwapState, swap_id)
        if swap_state is None:
            raise ValueError(f"Swap not found: {swap_id}")
        if swap_state.status != SwapStatus.OPEN.value:
            raise ValueError(f"Swap is not open (status={swap_state.status})")

        # Check timelock (block height based)
        current_height = _get_current_height(session, self.chain_id)
        if current_height >= swap_state.timelock:
            raise ValueError("Swap timelock expired")

        # Verify secret matches hashlock (matches aitbc.settlement.htlc.compute_hashlock)
        secret_hash = hashlib.sha256(secret.encode()).hexdigest()
        if secret_hash != swap_state.hashlock.replace("0x", "", 1):
            raise ValueError("Invalid secret: hash does not match hashlock")

        # Release from escrow to the participant, once the lock is confirmed.
        _require_locked(session, self.chain_id, swap_state)
        queue_protocol_transfer(
            sender=HTLC_CONTRACT_ADDRESS,
            recipient=swap_state.participant,
            amount=swap_state.amount,
            chain_id=self.chain_id,
            tx_type="HTLC_CLAIM",
            payload={"swap_id": swap_state.swap_id},
        )

        # Update swap state
        now = time.time()
        swap_state.status = SwapStatus.COMPLETED.value
        swap_state.secret = secret
        swap_state.completed_at = now
        session.add(swap_state)
        session.flush()

        logger.info(
            "HTLC swap completed: swap_id=%s participant=%s amount=%d",
            swap_id,
            swap_state.participant,
            swap_state.amount,
        )

        return HTLCSwapRecord(
            swap_id=swap_state.swap_id,
            initiator=swap_state.initiator,
            participant=swap_state.participant,
            token=swap_state.token,
            amount=swap_state.amount,
            hashlock=swap_state.hashlock,
            timelock=swap_state.timelock,
            status=SwapStatus.COMPLETED,
            secret=secret,
            created_at=swap_state.created_at,
            completed_at=now,
        )

    def refund_swap(self, session: Session, swap_id: str) -> HTLCSwapRecord:
        """Refund a swap after timelock expiry — return funds to initiator.

        Mirrors ``CrossChainAtomicSwap.refundSwap()``:
        - Validates swap is OPEN
        - Validates timelock has expired
        - Transfers funds from contract escrow back to initiator
        - Records swap state as REFUNDED

        Args:
            session: Active DB session.
            swap_id: The swap to refund.

        Returns:
            Updated HTLCSwapRecord.

        Raises:
            ValueError: If swap not found, not open, or timelock not expired.
        """
        swap_state = session.get(HTLCSwapState, swap_id)
        if swap_state is None:
            raise ValueError(f"Swap not found: {swap_id}")
        if swap_state.status != SwapStatus.OPEN.value:
            raise ValueError(f"Swap is not open (status={swap_state.status})")

        # Check timelock has expired
        current_height = _get_current_height(session, self.chain_id)
        if current_height < swap_state.timelock:
            raise ValueError("Swap timelock not yet expired")

        # Return escrowed funds to the initiator, once the lock is confirmed.
        _require_locked(session, self.chain_id, swap_state)
        queue_protocol_transfer(
            sender=HTLC_CONTRACT_ADDRESS,
            recipient=swap_state.initiator,
            amount=swap_state.amount,
            chain_id=self.chain_id,
            tx_type="HTLC_REFUND",
            payload={"swap_id": swap_state.swap_id},
        )

        # Update swap state
        now = time.time()
        swap_state.status = SwapStatus.REFUNDED.value
        swap_state.refunded_at = now
        session.add(swap_state)
        session.flush()

        logger.info(
            "HTLC swap refunded: swap_id=%s initiator=%s amount=%d",
            swap_id,
            swap_state.initiator,
            swap_state.amount,
        )

        return HTLCSwapRecord(
            swap_id=swap_state.swap_id,
            initiator=swap_state.initiator,
            participant=swap_state.participant,
            token=swap_state.token,
            amount=swap_state.amount,
            hashlock=swap_state.hashlock,
            timelock=swap_state.timelock,
            status=SwapStatus.REFUNDED,
            created_at=swap_state.created_at,
            refunded_at=now,
        )

    def get_swap(self, session: Session, swap_id: str) -> HTLCSwapRecord | None:
        """Get the current state of a swap.

        Returns:
            HTLCSwapRecord if found, None otherwise.
        """
        swap_state = session.get(HTLCSwapState, swap_id)
        if swap_state is None:
            return None
        return HTLCSwapRecord(
            swap_id=swap_state.swap_id,
            initiator=swap_state.initiator,
            participant=swap_state.participant,
            token=swap_state.token,
            amount=swap_state.amount,
            hashlock=swap_state.hashlock,
            timelock=swap_state.timelock,
            status=SwapStatus(swap_state.status),
            secret=swap_state.secret,
            created_at=swap_state.created_at,
            completed_at=swap_state.completed_at or 0.0,
            refunded_at=swap_state.refunded_at or 0.0,
        )
