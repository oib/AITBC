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

from enum import StrEnum

from sqlmodel import Session

from ..base_models import HTLCSwapState
from ..logger import get_logger
from ..protocol_escrow import htlc_escrow_address
from ..rpc.retired import raise_for_retired_contract

logger = get_logger(__name__)


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

    def __init__(self, chain_id: str) -> None:
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
        raise_for_retired_contract("HTLC (initiate_swap)")

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
        raise_for_retired_contract("HTLC (complete_swap)")

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
        raise_for_retired_contract("HTLC (refund_swap)")

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
