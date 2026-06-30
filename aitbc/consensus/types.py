"""Shared consensus types for multi-validator PoA + PBFT (v0.7.5 §A2).

These are dependency-free shared types that the CLI, governance service,
and other services can import without depending on ``apps/blockchain-node/``.
The blockchain node's consensus implementation (``MultiValidatorPoA``,
``PBFTConsensus``) mirrors these types internally.

The types cover:
- ``PBFTMessageType`` — enum for pre-prepare/prepare/commit/view-change
- ``PBFTMessageData`` — shared PBFT message dataclass (mirrors the
  node-internal ``PBFTMessage`` but without app dependencies)
- ``ConsensusConfig`` — configuration for multi-validator consensus
- ``ValidatorInfo`` — shared validator info for CLI/API consumption
- ``ValidatorRole`` — enum for proposer/validator/standby roles
- ``SlashingCondition`` — enum for slashing offense types
- ``SlashingEventData`` — shared slashing event dataclass
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PBFTMessageType(StrEnum):
    """PBFT message types for the 3-phase consensus protocol."""

    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    VIEW_CHANGE = "view_change"


class ValidatorRole(StrEnum):
    """Roles a validator can have in the consensus."""

    PROPOSER = "proposer"
    VALIDATOR = "validator"
    STANDBY = "standby"


class SlashingCondition(StrEnum):
    """Conditions that trigger validator slashing."""

    DOUBLE_SIGN = "double_sign"
    UNAVAILABLE = "unavailable"
    INVALID_BLOCK = "invalid_block"
    SLOW_RESPONSE = "slow_response"


@dataclass
class PBFTMessageData:
    """Shared PBFT message type — mirrors the node-internal PBFTMessage.

    This dataclass is dependency-free for CLI/SDK consumption. The
    blockchain node's ``PBFTConsensus`` uses an internal ``PBFTMessage``
    that mirrors these fields.

    The ``signature`` field is a 65-byte secp256k1 hex signature over
    the canonical-JSON of the message (excluding the signature field
    itself). See ``aitbc.crypto.consensus_signing``.
    """

    message_type: PBFTMessageType
    sender: str
    view_number: int
    sequence_number: int
    digest: str
    signature: str
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for JSON transport or signing."""
        return {
            "message_type": self.message_type.value,
            "sender": self.sender,
            "view_number": self.view_number,
            "sequence_number": self.sequence_number,
            "digest": self.digest,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict[str, Any], signature: str = "") -> PBFTMessageData:
        """Deserialize from a dict (signature provided separately)."""
        return PBFTMessageData(
            message_type=PBFTMessageType(data.get("message_type", "pre_prepare")),
            sender=data["sender"],
            view_number=int(data["view_number"]),
            sequence_number=int(data["sequence_number"]),
            digest=data["digest"],
            signature=signature or data.get("signature", ""),
            timestamp=float(data.get("timestamp", 0.0)),
        )


@dataclass
class ConsensusConfig:
    """Configuration for multi-validator consensus.

    This is the shared SDK config dataclass. The blockchain node's
    ``ChainSettings`` (``apps/blockchain-node/src/aitbc_chain/config.py``)
    has corresponding fields that are set from environment variables.
    """

    enabled: bool = False
    fault_tolerance: int = 1
    required_messages: int = 3
    view_change_timeout_seconds: int = 30
    consensus_round_timeout_seconds: int = 10
    validator_set_epoch_blocks: int = 7200  # epoch length for rotation
    slashing_enabled: bool = True
    slashing_amount: float = 100.0  # stake to slash per offense
    byzantine_threshold: int = 3  # slash count before deactivation
    max_view_change_backoff_seconds: int = 300  # cap for exponential backoff


@dataclass
class ValidatorInfo:
    """Shared validator info type for CLI/API consumption.

    This is a read-only projection of the node-internal ``Validator``
    dataclass, suitable for returning from RPC endpoints and displaying
    in the CLI without exposing the full internal state.
    """

    address: str
    stake: float
    reputation: float
    role: ValidatorRole = ValidatorRole.VALIDATOR
    is_active: bool = True
    last_proposed: int = 0
    epoch: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for JSON API responses."""
        return {
            "address": self.address,
            "stake": self.stake,
            "reputation": self.reputation,
            "role": self.role.value,
            "is_active": self.is_active,
            "last_proposed": self.last_proposed,
            "epoch": self.epoch,
        }


@dataclass
class SlashingEventData:
    """Shared slashing event dataclass for CLI/API consumption.

    Mirrors the node-internal ``SlashingEvent`` but dependency-free.
    """

    validator_address: str
    condition: SlashingCondition
    evidence: str
    block_height: int
    timestamp: float
    slash_amount: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for JSON API responses."""
        return {
            "validator_address": self.validator_address,
            "condition": self.condition.value,
            "evidence": self.evidence,
            "block_height": self.block_height,
            "timestamp": self.timestamp,
            "slash_amount": self.slash_amount,
        }


@dataclass
class ConsensusStatus:
    """Consensus status snapshot for CLI/API consumption.

    Returned by the ``consensus status`` CLI command and the
    blockchain-node consensus status RPC endpoint.
    """

    mode: str  # "single_validator" or "multi_validator"
    enabled: bool
    current_view: int = 0
    current_sequence: int = 0
    current_epoch: int = 0
    active_validators: int = 0
    total_validators: int = 0
    fault_tolerance: int = 0
    required_messages: int = 0
    slashing_events: int = 0
    view_changes: int = 0
    consensus_rounds: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for JSON API responses."""
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "current_view": self.current_view,
            "current_sequence": self.current_sequence,
            "current_epoch": self.current_epoch,
            "active_validators": self.active_validators,
            "total_validators": self.total_validators,
            "fault_tolerance": self.fault_tolerance,
            "required_messages": self.required_messages,
            "slashing_events": self.slashing_events,
            "view_changes": self.view_changes,
            "consensus_rounds": self.consensus_rounds,
        }
