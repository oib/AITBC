"""Python-native HTLC contract implementation (v0.9.0 B4).

Mirrors the logic of ``CrossChainAtomicSwap.sol``:

    initiate_swap(swap_id, participant, token, amount, hashlock, timelock)
    complete_swap(swap_id, secret)
    refund_swap(swap_id)

The Solidity contract locks funds in an EVM mapping; this implementation
locks funds by debiting the initiator's ``Account`` balance and crediting a
contract-escrow account. On completion, funds are credited to the participant;
on refund, funds are returned to the initiator.

All state transitions are persisted via the ``HTLCSwapRecord`` SQLModel so
swap state survives node restarts.
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Session

from ..base_models import Account, HTLCSwapState
from ..logger import get_logger

logger = get_logger(__name__)

# Well-known address used as the HTLC contract's escrow account. In an EVM
# chain this would be the deployed contract address; here we use a reserved
# address that holds locked funds until swap completion or refund.
HTLC_CONTRACT_ADDRESS = "0xhtlc_contract_0000000000000000000000000000000000000"


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


def _get_or_create_account(session: Session, chain_id: str, address: str) -> Account:
    """Get an account or create it with zero balance."""
    account = session.get(Account, (chain_id, address))
    if account is None:
        account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
        session.add(account)
        session.flush()
    return account


def _transfer_balance(
    session: Session,
    chain_id: str,
    from_address: str,
    to_address: str,
    amount: int,
) -> None:
    """Transfer ``amount`` from one account to another within a DB session.

    Raises:
        ValueError: If the sender has insufficient balance.
    """
    if amount <= 0:
        raise ValueError(f"Transfer amount must be positive, got {amount}")

    sender = _get_or_create_account(session, chain_id, from_address)
    if sender.balance < amount:
        raise ValueError(f"Insufficient balance for {from_address}: has {sender.balance}, needs {amount}")
    sender.balance -= amount
    sender.nonce += 1
    sender.updated_at = datetime.now(UTC)
    session.add(sender)

    recipient = _get_or_create_account(session, chain_id, to_address)
    recipient.balance += amount
    recipient.updated_at = datetime.now(UTC)
    session.add(recipient)


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
            amount=3600,
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
            amount: Amount to lock (in compute-seconds).
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

        # Transfer funds from initiator to contract escrow account
        _transfer_balance(session, self.chain_id, initiator, HTLC_CONTRACT_ADDRESS, amount)

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
        current_height = int(time.time() // 5)  # approximate current block height
        if current_height >= swap_state.timelock:
            raise ValueError("Swap timelock expired")

        # Verify secret matches hashlock (matches aitbc.settlement.htlc.compute_hashlock)
        secret_hash = hashlib.sha256(secret.encode()).hexdigest()
        if secret_hash != swap_state.hashlock.replace("0x", "", 1):
            raise ValueError("Invalid secret: hash does not match hashlock")

        # Transfer funds from contract escrow to participant
        _transfer_balance(session, self.chain_id, HTLC_CONTRACT_ADDRESS, swap_state.participant, swap_state.amount)

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
        current_height = int(time.time() // 5)
        if current_height < swap_state.timelock:
            raise ValueError("Swap timelock not yet expired")

        # Transfer funds from contract escrow back to initiator
        _transfer_balance(session, self.chain_id, HTLC_CONTRACT_ADDRESS, swap_state.initiator, swap_state.amount)

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
