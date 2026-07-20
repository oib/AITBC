"""Shared dependencies for the Developer Platform routers."""

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from ...governance.services.governance_service import GovernanceService
from ....storage.db import get_session
from ..services.developer_platform_service import DeveloperPlatformService


def get_developer_platform_service(session: Annotated[Session, Depends(get_session)]) -> DeveloperPlatformService:
    """Get a DeveloperPlatformService instance."""
    return DeveloperPlatformService(session)


def get_governance_service(session: Annotated[Session, Depends(get_session)]) -> GovernanceService:
    """Get a GovernanceService instance."""
    return GovernanceService(session)
