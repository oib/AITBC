"""Developer registry request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeveloperCreate(BaseModel):
    """Payload for registering a developer."""

    wallet_address: str
    name: str | None = None
    email: str | None = None
    github_handle: str | None = None


class DeveloperUpdate(BaseModel):
    """Payload for updating a developer profile."""

    name: str | None = None
    email: str | None = None
    github_handle: str | None = None
    is_active: bool | None = None


class DeveloperResponse(BaseModel):
    """Developer registry response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    wallet_address: str
    name: str | None
    email: str | None
    github_handle: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
