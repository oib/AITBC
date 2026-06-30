"""AITBC shared consensus types (v0.7.5).

Provides dependency-free consensus types for multi-validator PoA + PBFT.
These are consumed by the CLI, governance service, and other services
that need to display or query consensus state without depending on
``apps/blockchain-node/``.

The blockchain node's consensus implementation (``MultiValidatorPoA``,
``PBFTConsensus``) mirrors these types internally.

Provides:
- ``PBFTMessageType``: enum for pre-prepare/prepare/commit/view-change
- ``ValidatorRole``: enum for proposer/validator/standby roles
- ``SlashingCondition``: enum for slashing offense types
- ``PBFTMessageData``: shared PBFT message dataclass
- ``ConsensusConfig``: multi-validator consensus configuration
- ``ValidatorInfo``: shared validator info for CLI/API
- ``SlashingEventData``: shared slashing event for CLI/API
- ``ConsensusStatus``: consensus status snapshot for CLI/API
"""

from __future__ import annotations

from .types import (
    ConsensusConfig,
    ConsensusStatus,
    PBFTMessageData,
    PBFTMessageType,
    SlashingCondition,
    SlashingEventData,
    ValidatorInfo,
    ValidatorRole,
)

__all__ = [
    "ConsensusConfig",
    "ConsensusStatus",
    "PBFTMessageData",
    "PBFTMessageType",
    "SlashingCondition",
    "SlashingEventData",
    "ValidatorInfo",
    "ValidatorRole",
]
