"""Shared core types for DAO grants (v0.16.1 §A1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from .developer import DeveloperProfile


@dataclass
class GrantMilestone:
    """A milestone within a grant proposal."""

    milestone_id: str = ""
    grant_id: str = ""
    title: str = ""
    description: str = ""
    amount: Decimal = Decimal("0")
    status: str = "pending"
    due_date: datetime | None = None
    completed_at: datetime | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class GrantProposal:
    """Core grant proposal data used by registry services and the CLI."""

    grant_id: str = ""
    developer: DeveloperProfile = field(default_factory=DeveloperProfile)
    title: str = ""
    description: str = ""
    requested_amount: Decimal = Decimal("0")
    approved_amount: Decimal = Decimal("0")
    disbursed_amount: Decimal = Decimal("0")
    status: str = "draft"
    votes_for: float = 0.0
    votes_against: float = 0.0
    votes_abstain: float = 0.0
    quorum: float = 0.0
    passing_threshold: float = 0.5
    milestones: list[GrantMilestone] = field(default_factory=list)
    voting_starts: datetime | None = None
    voting_ends: datetime | None = None
    executed_at: datetime | None = None
    proposal_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
