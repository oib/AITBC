"""Developer registry service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlmodel import Session

from ..domain.developer import Developer
from ..schemas.developer import DeveloperCreate, DeveloperUpdate


class DeveloperService:
    """CRUD and lookup operations for the developer registry."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def register(self, request: DeveloperCreate) -> Developer:
        """Register a new developer."""
        existing = (
            self.session.execute(
                select(Developer).where(Developer.wallet_address == request.wallet_address)  # type: ignore[arg-type]
            )
            .scalars()
            .one_or_none()
        )
        if existing:
            raise ValueError("Developer already registered for this wallet")
        developer = Developer(
            wallet_address=request.wallet_address,
            name=request.name,
            email=request.email,
            github_handle=request.github_handle,
        )
        self.session.add(developer)
        self.session.commit()
        self.session.refresh(developer)
        return developer

    async def get_by_wallet(self, wallet_address: str) -> Developer | None:
        """Get a developer by wallet address."""
        return (
            self.session.execute(
                select(Developer).where(Developer.wallet_address == wallet_address)  # type: ignore[arg-type]
            )
            .scalars()
            .one_or_none()
        )

    async def list(self, limit: int = 100, offset: int = 0, active_only: bool = True) -> list[Developer]:
        """List registered developers."""
        stmt = select(Developer)
        if active_only:
            stmt = stmt.where(Developer.is_active == True)  # type: ignore[arg-type]  # noqa: E712
        stmt = stmt.order_by(Developer.created_at.desc()).limit(limit).offset(offset)  # type: ignore[attr-defined]
        return list(self.session.execute(stmt).scalars().all())

    async def update(self, wallet_address: str, request: DeveloperUpdate) -> Developer:
        """Update a developer profile."""
        developer = await self.get_by_wallet(wallet_address)
        if not developer:
            raise ValueError("Developer not found")
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(developer, field, value)
        developer.updated_at = datetime.now(UTC)
        self.session.add(developer)
        self.session.commit()
        self.session.refresh(developer)
        return developer
