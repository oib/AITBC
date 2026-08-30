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

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging

from ..config import settings
from .multi_validator_poa import MultiValidatorPoA

logger = get_logger(__name__)


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
    block_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_type": self.message_type.value,
            "sender": self.sender,
            "view_number": self.view_number,
            "sequence_number": self.sequence_number,
            "digest": self.digest,
            "signature": self.signature,
            "timestamp": self.timestamp,
            "block_hash": self.block_hash,
        }


@dataclass
class PBFTState:
    current_view: int
    current_sequence: int
    prepared_messages: dict[str, list[PBFTMessage]]
    committed_messages: dict[str, list[PBFTMessage]]
    pre_prepare_messages: dict[str, PBFTMessage]


class PBFTConsensus:
    """PBFT consensus implementation"""

    def __init__(
        self,
        consensus: MultiValidatorPoA,
        private_key: str = "",
        chain_id: str = "ait-hub",
        local_validator: str = "",
        sync_manager: Any | None = None,
    ):
        if not settings.multi_validator_consensus_enabled:
            raise RuntimeError(
                "PBFTConsensus is not yet activated. "
                "Set multi_validator_consensus_enabled=true in config to enable (requires security review)."
            )
        self.consensus = consensus
        self._private_key = private_key
        self._chain_id = chain_id
        self._local_validator = local_validator
        self._sync_manager: Any | None = sync_manager
        self._gossip_backend: Any = None
        self._consensus_timer: asyncio.Task[None] | None = None
        self._view_change_count = 0
        self._message_event = asyncio.Event()
        self._local_prepared: set[str] = set()
        self._local_committed: set[str] = set()
        self.state = PBFTState(
            current_view=0, current_sequence=0, prepared_messages={}, committed_messages={}, pre_prepare_messages={}
        )
        self.fault_tolerance = max(1, len(consensus.get_consensus_participants()) // 3)
        self.required_messages = 2 * self.fault_tolerance + 1
        self._on_execute: Any = None

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
            block_hash=block_hash,
        )
        # B6: sign the pre-prepare message with the sender's private key
        self._sign_message(message)

        # Store pre-prepare message
        key = f"{sequence}:{view}"
        self.state.pre_prepare_messages[key] = message

        # Broadcast to all validators
        await self._broadcast_message(message)

        self._message_event.set()
        return True

    async def _ensure_synced(self) -> bool:
        """Ask SyncManager to catch up and wait until the gap is small."""
        if self._sync_manager is None or not settings.sync_manager_enabled:
            return True
        max_gap = getattr(settings, "sync_manager_max_proposal_gap", 2)
        timeout = getattr(settings, "sync_manager_proposal_sync_timeout", 30)
        status = self._sync_manager.get_sync_status(self._chain_id)
        if status.get("gap", 0) <= max_gap:
            return True
        logger.warning("PBFT sync gap %s exceeds %s on chain %s, forcing catch-up", status.get("gap"), max_gap, self._chain_id)
        await self._sync_manager.force_catch_up(self._chain_id)
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self._sync_manager.get_sync_status(self._chain_id)
            if status.get("gap", 0) <= max_gap:
                return True
            try:
                await asyncio.wait_for(asyncio.sleep(1), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        logger.warning("PBFT timed out waiting for sync on chain %s", self._chain_id)
        return False

    async def propose_and_wait(self, proposer: str, block_hash: str, timeout: float | None = None) -> bool:
        """Run the full PBFT proposal pipeline for the local proposer.

        Waits for a prepare quorum and then a commit quorum before returning.
        The caller writes the block only when this returns True.
        """
        if not await self._ensure_synced():
            return False

        if not self._local_validator:
            self._local_validator = proposer
        # Capture the sequence/view before pre-prepare broadcasts trigger commits
        pre_prepare_sequence = self.state.current_sequence + 1
        pre_prepare_view = self.state.current_view
        key = f"{pre_prepare_sequence}:{pre_prepare_view}"
        await self.pre_prepare_phase(proposer, block_hash)
        pre_prepare_msg = self.state.pre_prepare_messages.get(key)
        if not pre_prepare_msg:
            return False

        # Send our own prepare; it will trigger a local commit once a prepare quorum forms
        await self.prepare_phase(self._local_validator, pre_prepare_msg)

        # Wait for enough prepares (other validators respond via handle_incoming_message)
        deadline = time.time() + timeout if timeout else None
        while len(self.state.prepared_messages.get(key, [])) < self.required_messages:
            if deadline and time.time() > deadline:
                logger.warning("PBFT prepare quorum timeout for key %s", key)
                return False
            self._message_event.clear()
            try:
                await asyncio.wait_for(self._message_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

        # Wait for enough commits
        while len(self.state.committed_messages.get(key, [])) < self.required_messages:
            if deadline and time.time() > deadline:
                logger.warning("PBFT commit quorum timeout for key %s", key)
                return False
            self._message_event.clear()
            try:
                await asyncio.wait_for(self._message_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

        return True

    async def prepare_phase(self, validator: str, pre_prepare_msg: PBFTMessage) -> bool:
        """Phase 2: Prepare"""
        # B6: verify the incoming pre-prepare message signature
        if not self._verify_message_signature(pre_prepare_msg):
            return False

        key = f"{pre_prepare_msg.sequence_number}:{pre_prepare_msg.view_number}"

        if key not in self.state.pre_prepare_messages:
            return False

        # Only the local validator sends one prepare per key
        if validator == self._local_validator:
            if key in self._local_prepared:
                return len(self.state.prepared_messages.get(key, [])) >= self.required_messages
            self._local_prepared.add(key)

        # Create prepare message
        prepare_msg = PBFTMessage(
            message_type=PBFTMessageType.PREPARE,
            sender=validator,
            view_number=pre_prepare_msg.view_number,
            sequence_number=pre_prepare_msg.sequence_number,
            digest=pre_prepare_msg.digest,
            signature="",
            timestamp=time.time(),
            block_hash=pre_prepare_msg.block_hash,
        )
        # B6: sign the prepare message with the sender's private key
        self._sign_message(prepare_msg)

        # Store prepare message
        if key not in self.state.prepared_messages:
            self.state.prepared_messages[key] = []
        self.state.prepared_messages[key].append(prepare_msg)

        # Broadcast prepare message
        await self._broadcast_message(prepare_msg)

        self._message_event.set()

        # Check if we have enough prepare messages and trigger commit
        if len(self.state.prepared_messages[key]) >= self.required_messages:
            if self._local_validator:
                await self._maybe_send_commit(key)
            return True
        return False

    async def commit_phase(self, validator: str, prepare_msg: PBFTMessage) -> bool:
        """Phase 3: Commit"""
        # B6: verify the incoming prepare message signature
        if not self._verify_message_signature(prepare_msg):
            return False

        key = f"{prepare_msg.sequence_number}:{prepare_msg.view_number}"

        if validator == self._local_validator:
            if key in self._local_committed:
                return len(self.state.committed_messages.get(key, [])) >= self.required_messages
            self._local_committed.add(key)

        # Create commit message
        commit_msg = PBFTMessage(
            message_type=PBFTMessageType.COMMIT,
            sender=validator,
            view_number=prepare_msg.view_number,
            sequence_number=prepare_msg.sequence_number,
            digest=prepare_msg.digest,
            signature="",
            timestamp=time.time(),
            block_hash=prepare_msg.block_hash,
        )
        # B6: sign the commit message with the sender's private key
        self._sign_message(commit_msg)

        # Store commit message
        if key not in self.state.committed_messages:
            self.state.committed_messages[key] = []
        self.state.committed_messages[key].append(commit_msg)

        # Broadcast commit message
        await self._broadcast_message(commit_msg)

        self._message_event.set()

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

        # Notify the block production path that consensus is complete
        if self._on_execute:
            try:
                pp = self.state.pre_prepare_messages.get(key)
                if pp:
                    await self._on_execute(pp.block_hash, self.state.committed_messages.get(key, []))
            except Exception:
                logger.exception("PBFT on_execute callback failed for key %s", key)

        return True

    def get_certificate(self, block_hash: str, view: int | None = None) -> list[dict[str, Any]]:
        """Return the commit certificate for a completed PBFT round.\n\n        Searches across all views and sequences for commit messages matching\n        the requested block hash, so a certificate is still retrievable after\n        a view change during the proposal round.\n"""
        certificate = []
        for messages in self.state.committed_messages.values():
            for m in messages:
                if m.block_hash == block_hash:
                    certificate.append(m.to_dict())
        # De-duplicate by sender to keep certificates compact.
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for msg in certificate:
            sender = msg.get("sender", "")
            if sender and sender in seen:
                continue
            seen.add(sender)
            deduped.append(msg)
        return deduped

    def set_on_execute(self, callback: Any) -> None:
        """Set the callback executed when a commit quorum is reached.

        The callback receives the block hash and the list of commit messages.
        """
        self._on_execute = callback

    async def _maybe_send_commit(self, key: str) -> bool:
        """Send a local commit message if we have a prepare quorum and have not yet committed."""
        prepared = self.state.prepared_messages.get(key, [])
        if len(prepared) < self.required_messages:
            return False
        if key in self._local_committed:
            return True

        # Use any prepare message to derive the commit fields
        base = prepared[0]
        return await self.commit_phase(self._local_validator, base)

    async def _broadcast_message(self, message: PBFTMessage) -> None:
        """Broadcast message once to the shared gossip topic."""
        await self._send_to_validator(message)

    async def _send_to_validator(self, message: PBFTMessage) -> None:
        """Send message to the shared gossip backend; subscribers deliver to each validator."""
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
            "block_hash": message.block_hash,
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
        if self._sync_manager is not None and settings.sync_manager_enabled:
            create_task_with_logging(
                self._sync_manager.force_catch_up(self._chain_id), name=f"pbft_view_change_sync_{self._chain_id}"
            )
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

        Rejects unsigned messages unless ``pbft_require_signatures`` is
        explicitly disabled in config (testing only). Signed messages are
        verified cryptographically regardless of whether this node has its
        own signing key — verification only needs the signer's address.
        """
        if not message.signature:
            return not settings.pbft_require_signatures
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

    async def handle_incoming_message(self, message_data: dict[str, Any]) -> None:
        """Handle an incoming gossip message (B7/C5).

        Reconstructs a :class:`PBFTMessage` from the dict, verifies its
        signature, and routes it to the appropriate phase handler based
        on ``message_type``. When enough prepare or commit messages are
        collected, it triggers the next PBFT phase for the local validator.
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
                block_hash=message_data.get("block_hash", ""),
            )
        except (KeyError, ValueError):
            return  # malformed message — drop

        # B6: verify the signature before processing
        if not self._verify_message_signature(message):
            return

        key = f"{message.sequence_number}:{message.view_number}"

        # Route to the appropriate phase handler
        if message.message_type == PBFTMessageType.PRE_PREPARE:
            self.state.pre_prepare_messages[key] = message
            self._message_event.set()
            # As a validator, respond with a prepare for this pre-prepare
            if self._local_validator and message.sender != self._local_validator and key not in self._local_prepared:
                await self.prepare_phase(self._local_validator, message)
        elif message.message_type == PBFTMessageType.PREPARE:
            if key not in self.state.prepared_messages:
                self.state.prepared_messages[key] = []
            if any(m.sender == message.sender for m in self.state.prepared_messages[key]):
                return  # ignore duplicate prepare from same sender
            self.state.prepared_messages[key].append(message)
            self._message_event.set()
            if self._local_validator:
                await self._maybe_send_commit(key)
        elif message.message_type == PBFTMessageType.COMMIT:
            if key not in self.state.committed_messages:
                self.state.committed_messages[key] = []
            if any(m.sender == message.sender for m in self.state.committed_messages[key]):
                return  # ignore duplicate commit from same sender
            self.state.committed_messages[key].append(message)
            self._message_event.set()
            if len(self.state.committed_messages[key]) >= self.required_messages:
                await self.execute_phase(key)

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
        self._consensus_timer = create_task_with_logging(self._on_timeout(timeout), name="pbft_consensus_timer")

    async def _on_timeout(self, delay: float) -> None:
        """H6: callback fired when the consensus timer elapses — triggers a view change."""
        await asyncio.sleep(delay)
        self.handle_view_change(self.state.current_view + 1)

    def _cancel_consensus_timer(self) -> None:
        """H6: cancel any pending consensus (view change) timer."""
        if self._consensus_timer and not self._consensus_timer.done():
            self._consensus_timer.cancel()
        self._consensus_timer = None
