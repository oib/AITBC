"""Shared core types for the developer registry (v0.16.1 §A1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ReputationScore:
    """A reputation score for a developer."""

    score: float = 0.0
    review_count: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectListing:
    """A project published by a developer."""

    project_id: str
    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    url: str = ""
    created_at: datetime | None = None


@dataclass
class DeveloperProfile:
    """Core developer profile data used by registry services and the CLI."""

    developer_id: str = ""
    wallet_address: str = ""
    name: str = ""
    email: str = ""
    github_handle: str = ""
    bio: str = ""
    projects: list[ProjectListing] = field(default_factory=list)
    reputation: ReputationScore = field(default_factory=ReputationScore)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)
