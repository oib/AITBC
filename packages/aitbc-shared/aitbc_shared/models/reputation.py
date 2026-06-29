"""
Shared Reputation DTO

Provides a context-agnostic data transfer object for agent reputation data,
so contexts (e.g. certification) can consume reputation metrics without
importing the reputation context's ORM model (`AgentReputation`).

This breaks the cross-context import dependency flagged in v0.5.19:
certification services previously imported `AgentReputation` directly from
`reputation.services.reputation_service`, coupling the two bounded contexts
at the ORM layer. The reputation context should expose a `to_dto()` converter
that produces this DTO; consumers depend only on the DTO.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ReputationDTO:
    """DTO for cross-context reputation data access.

    Mirrors the subset of `AgentReputation` fields that other contexts
    (certification, partnership, badge) read. It intentionally carries no
    ORM metadata and no write surface — it is a read-only projection.

    Field defaults match `AgentReputation` defaults so a freshly-initialised
    agent has a valid DTO without the producer needing to fill every field.
    """

    agent_id: str
    trust_score: float = 500.0  # 0-1000 scale
    reputation_level: str = "beginner"
    performance_rating: float = 3.0  # 1-5 stars
    reliability_score: float = 50.0  # 0-100%
    community_rating: float = 3.0  # 1-5 stars

    # Economic metrics
    total_earnings: float = 0.0
    transaction_count: int = 0
    success_rate: float = 0.0  # 0-100%
    dispute_count: int = 0
    dispute_won_count: int = 0

    # Activity metrics
    jobs_completed: int = 0
    jobs_failed: int = 0
    average_response_time: float = 0.0  # milliseconds
    uptime_percentage: float = 0.0  # 0-100%
    community_contributions: int = 0

    # Geographic and service info
    geographic_region: str = ""
    service_categories: list[str] = field(default_factory=list)
    specialization_tags: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_activity: datetime | None = None
