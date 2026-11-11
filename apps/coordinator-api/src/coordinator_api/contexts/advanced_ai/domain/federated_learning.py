"""
Federated Learning Domain Models

Domain models for managing cross-agent knowledge sharing and collaborative model training.
"""

from __future__ import annotations

from enum import StrEnum


class TrainingStatus(StrEnum):
    INITIALIZED = "initiated"
    GATHERING_PARTICIPANTS = "gathering_participants"
    TRAINING = "training"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class ParticipantStatus(StrEnum):
    INVITED = "invited"
    JOINED = "joined"
    TRAINING = "training"
    SUBMITTED = "submitted"
    DROPPED = "dropped"


__all__ = [
    "ParticipantStatus",
    "TrainingStatus",
]
