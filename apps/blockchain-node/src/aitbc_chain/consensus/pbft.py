"""
Practical Byzantine Fault Tolerance (PBFT) Consensus Implementation
Provides Byzantine fault tolerance for up to 1/3 faulty validators

# ════════════════════════════════════════════════════════════════
# v0.7.5: All 5 security review findings fixed (C4-C5, H4-H6).
# Guard now reads from settings.multi_validator_consensus_enabled
# instead of MULTI_VALIDATOR_CONSENSUS_ENABLED env var.
# Keep guard in place until B14 test suite passes.
# ════════════════════════════════════════════════════════════════
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..config import settings
from .multi_validator_poa import MultiValidatorPoA


class PBFTPhase(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    EXECUTE = "execute"


class PBFTMessageType(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    VIEW_CHANGE = "view_change"


@dataclass
class PBFTMessage:
    message_type: PBFTMessageType
    sender: str
    view_number: int
    sequence_number: int
    digest: str
    signature: str
    timestamp: float


@dataclass
class PBFTState:
    current_view: int
    current_sequence: int
    prepared_messages: dict[str, list[PBFTMessage]]
    committed_messages: dict[str, list[PBFTMessage]]
    pre_prepare_messages: dict[str, PBFTMessage]


class PBFTConsensus:
    """PBFT consensus implementation"""

    def __init__(self, consensus: MultiValidatorPoA, private_key: str = "", chain_id: str = "ait-hub"):
        if not settings.multi_validator_consensus_enabled:
            raise RuntimeError(
                "PBFTConsensus is not yet activated. "
                "Set multi_validator_consensus_enabled=true in config to enable (requires security review)."
            )
        self.consensus = consensus
        self._private_key = private_key
        self._chain_id = chain_id
        self._gossip_backend: Any = None
        self._consensus_timer: asyncio.Task[None] | None = None
        self._view_change_count = 0
        self.state = PBFTState(
            current_view=0, current_sequence=0, prepared_messages={}, committed_messages={}, pre_prepare_messages={}
        )
        self.fault_tolerance = max(1, len(consensus.get_consensus_participants()) // 3)
        self.required_messages = 2 * self.fault_tolerance + 1

    def get_message_digest(self, block_hash: str, sequence: int, view: int) -> str:
        """Generate message digest for PBFT"""
        content = f"{block_hash}:{sequence}:{view}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def pre_prepare_phase(self, proposer: str, block_hash: str) -> bool:
        """Phase 1: Pre-prepare"""
        # H4: recalculate fault tolerance in case validator set changed
        self._recalculate_fault_tolerance()
        # H6: start consensus timer (view change timeout)
        self._start_consensus_timer()

        sequence = self.state.current_sequence + 1
        view = self.state.current_view
        digest = self.get_message_digest(block_hash, sequence, view)

        message = PBFTMessage(
            message_type=PBFTMessageType.PRE_PREPARE,
            sender=proposer,
            view_number=view,
            sequence_number=sequence,
            digest=digest,
            signature="",
            timestamp=time.time(),
        )
        # B6: sign the pre-prepare message with the sender's private key
        self._sign_message(message)

        # Store pre-prepare message
        key = f"{sequence}:{view}"
        self.state.pre_prepare_messages[key] = message

        # Broadcast to all validators
        await self._broadcast_message(message)
        return True

    async def prepare_phase(self, validator: str, pre_prepare_msg: PBFTMessage) -> bool:
        """Phase 2: Prepare"""
        # B6: verify the incoming pre-prepare message signature
        if not self._verify_message_signature(pre_prepare_msg):
            return False

        key = f"{pre_prepare_msg.sequence_number}:{pre_prepare_msg.view_number}"

        if key not in self.state.pre_prepare_messages:
            return False

        # Create prepare message
        prepare_msg = PBFTMessage(
            message_type=PBFTMessageType.PREPARE,
            sender=validator,
            view_number=pre_prepare_msg.view_number,
            sequence_number=pre_prepare_msg.sequence_number,
            digest=pre_prepare_msg.digest,
            signature="",
            timestamp=time.time(),
        )
        # B6: sign the prepare message with the sender's private key
        self._sign_message(prepare_msg)

        # Store prepare message
        if key not in self.state.prepared_messages:
            self.state.prepared_messages[key] = []
        self.state.prepared_messages[key].append(prepare_msg)

        # Broadcast prepare message
        await self._broadcast_message(prepare_msg)

        # Check if we have enough prepare messages
        return len(self.state.prepared_messages[key]) >= self.required_messages

    async def commit_phase(self, validator: str, prepare_msg: PBFTMessage) -> bool:
        """Phase 3: Commit"""
        # B6: verify the incoming prepare message signature
        if not self._verify_message_signature(prepare_msg):
            return False

        key = f"{prepare_msg.sequence_number}:{prepare_msg.view_number}"

        # Create commit message
        commit_msg = PBFTMessage(
            message_type=PBFTMessageType.COMMIT,
            sender=validator,
            view_number=prepare_msg.view_number,
            sequence_number=prepare_msg.sequence_number,
            digest=prepare_msg.digest,
            signature="",
            timestamp=time.time(),
        )
        # B6: sign the commit message with the sender's private key
        self._sign_message(commit_msg)

        # Store commit message
        if key not in self.state.committed_messages:
            self.state.committed_messages[key] = []
        self.state.committed_messages[key].append(commit_msg)

        # Broadcast commit message
        await self._broadcast_message(commit_msg)

        # Check if we have enough commit messages
        if len(self.state.committed_messages[key]) >= self.required_messages:
            return await self.execute_phase(key)

        return False

    async def execute_phase(self, key: str) -> bool:
        """Phase 4: Execute"""
        # Extract sequence and view from key
        sequence, view = map(int, key.split(":"))

        # Update state
        self.state.current_sequence = sequence

        # H6: consensus completed — cancel the view change timer
        self._cancel_consensus_timer()

        # Clean up old messages
        self._cleanup_messages(sequence)

        return True

    async def _broadcast_message(self, message: PBFTMessage) -> None:
        """Broadcast message to all validators"""
        validators = self.consensus.get_consensus_participants()

        for validator in validators:
            if validator != message.sender:
                # In real implementation, this would send over network
                await self._send_to_validator(validator, message)

    async def _send_to_validator(self, validator: str, message: PBFTMessage) -> None:
        """Send message to specific validator via gossip backend."""
        if self._gossip_backend is None:
            return  # no-op when no gossip backend is set (for testing)
        topic = f"pbft.{message.message_type.value}.{self._chain_id}"
        msg_data = {
            "message_type": message.message_type.value,
            "sender": message.sender,
            "view_number": message.view_number,
            "sequence_number": message.sequence_number,
            "digest": message.digest,
            "signature": message.signature,
            "timestamp": message.timestamp,
        }
        await self._gossip_backend.publish(topic, msg_data)

    def _cleanup_messages(self, sequence: int) -> None:
        """Clean up old messages to prevent memory leaks"""
        old_keys = [key for key in self.state.prepared_messages.keys() if int(key.split(":")[0]) < sequence]

        for key in old_keys:
            self.state.prepared_messages.pop(key, None)
            self.state.committed_messages.pop(key, None)
            self.state.pre_prepare_messages.pop(key, None)

    def handle_view_change(self, new_view: int) -> bool:
        """Handle view change when proposer fails (H5: safe view change)."""
        self.state.current_view = new_view
        self._view_change_count += 1
        # H5: Preserve prepared certificates for committed sequences
        committed_seq = self.state.current_sequence
        # Only clear messages for sequences > current_sequence (uncommitted)
        keys_to_clear = [key for key in list(self.state.prepared_messages.keys()) if int(key.split(":")[0]) > committed_seq]
        for key in keys_to_clear:
            self.state.prepared_messages.pop(key, None)
            self.state.pre_prepare_messages.pop(key, None)
        # Don't clear committed_messages — they're done
        # Clear uncommitted pre_prepare messages
        pp_to_clear = [key for key in list(self.state.pre_prepare_messages.keys()) if int(key.split(":")[0]) > committed_seq]
        for key in pp_to_clear:
            self.state.pre_prepare_messages.pop(key, None)
        return True

    # ------------------------------------------------------------------
    # B6: PBFT message signatures (C4)
    # ------------------------------------------------------------------

    def _sign_message(self, message: PBFTMessage) -> None:
        """Sign a PBFT message in place with the sender's private key.

        Only signs when ``self._private_key`` is non-empty. The signed
        payload is the canonical message dict (message_type, sender,
        view_number, sequence_number, digest) — matching the dict
        verified by ``_verify_message_signature()``.
        """
        if not self._private_key:
            return
        from aitbc.crypto.consensus_signing import sign_consensus_message

        msg_data = {
            "message_type": message.message_type.value,
            "sender": message.sender,
            "view_number": message.view_number,
            "sequence_number": message.sequence_number,
            "digest": message.digest,
        }
        message.signature = sign_consensus_message(msg_data, self._private_key)

    def _verify_message_signature(self, message: PBFTMessage) -> bool:
        """Verify a PBFT message signature (B6/C4).

        Rejects unsigned messages. When ``self._private_key`` is empty
        (no signing configured), unsigned messages are accepted for
        backwards-compatible testing.
        """
        if not self._private_key:
            return True  # no signing configured — accept unsigned (testing)
        if not message.signature:
            return False  # reject unsigned messages when signing is configured
        from aitbc.crypto.consensus_signing import verify_consensus_message

        msg_data = {
            "message_type": message.message_type.value,
            "sender": message.sender,
            "view_number": message.view_number,
            "sequence_number": message.sequence_number,
            "digest": message.digest,
        }
        return verify_consensus_message(msg_data, message.signature, message.sender)

    # ------------------------------------------------------------------
    # B7: Gossip network transport (C5)
    # ------------------------------------------------------------------

    def set_gossip_backend(self, backend: Any) -> None:
        """Set the gossip backend used for broadcasting PBFT messages."""
        self._gossip_backend = backend

    def handle_incoming_message(self, message_data: dict[str, Any]) -> None:
        """Handle an incoming gossip message (B7/C5).

        Reconstructs a :class:`PBFTMessage` from the dict, verifies its
        signature, and routes it to the appropriate phase handler based
        on ``message_type``.
        """
        try:
            message = PBFTMessage(
                message_type=PBFTMessageType(message_data["message_type"]),
                sender=message_data["sender"],
                view_number=message_data["view_number"],
                sequence_number=message_data["sequence_number"],
                digest=message_data["digest"],
                signature=message_data.get("signature", ""),
                timestamp=message_data.get("timestamp", time.time()),
            )
        except (KeyError, ValueError):
            return  # malformed message — drop

        # B6: verify the signature before processing
        if not self._verify_message_signature(message):
            return

        # Route to the appropriate phase handler
        if message.message_type == PBFTMessageType.PRE_PREPARE:
            key = f"{message.sequence_number}:{message.view_number}"
            self.state.pre_prepare_messages[key] = message
        elif message.message_type == PBFTMessageType.PREPARE:
            key = f"{message.sequence_number}:{message.view_number}"
            if key not in self.state.prepared_messages:
                self.state.prepared_messages[key] = []
            self.state.prepared_messages[key].append(message)
        elif message.message_type == PBFTMessageType.COMMIT:
            key = f"{message.sequence_number}:{message.view_number}"
            if key not in self.state.committed_messages:
                self.state.committed_messages[key] = []
            self.state.committed_messages[key].append(message)

    # ------------------------------------------------------------------
    # B10: View change fixes (H4 + H6)
    # ------------------------------------------------------------------

    def _recalculate_fault_tolerance(self) -> None:
        """H4: dynamically recalculate fault tolerance from the current validator set."""
        participants = self.consensus.get_consensus_participants()
        self.fault_tolerance = max(1, len(participants) // 3)
        self.required_messages = 2 * self.fault_tolerance + 1

    def _start_consensus_timer(self) -> None:
        """H6: start the consensus (view change) timer with exponential backoff."""
        self._cancel_consensus_timer()
        timeout = settings.consensus_view_change_timeout_seconds
        # Exponential backoff: timeout * 2^view_change_count, capped at 300s
        timeout = min(timeout * (2**self._view_change_count), 300)
        self._consensus_timer = asyncio.create_task(self._on_timeout(timeout))

    async def _on_timeout(self, delay: float) -> None:
        """H6: callback fired when the consensus timer elapses — triggers a view change."""
        await asyncio.sleep(delay)
        self.handle_view_change(self.state.current_view + 1)

    def _cancel_consensus_timer(self) -> None:
        """H6: cancel any pending consensus (view change) timer."""
        if self._consensus_timer and not self._consensus_timer.done():
            self._consensus_timer.cancel()
        self._consensus_timer = None
