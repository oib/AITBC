from typing import Callable, Generator, Annotated
from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from .config import settings


def get_session() -> Generator[Session, None, None]:
    """Get database session"""
    from .database import engine
    with Session(engine) as session:
        yield session


# Type alias for session dependency
SessionDep = Annotated[Session, Depends(get_session)]


class APIKeyValidator:
    def __init__(self, allowed_keys: list[str]):
        self.allowed_keys = {key.strip() for key in allowed_keys if key}

    def __call__(self, api_key: str | None = Header(default=None, alias="X-Api-Key")) -> str:
        if not api_key or api_key not in self.allowed_keys:
            raise HTTPException(status_code=401, detail="invalid api key")
        return api_key


def require_client_key() -> Callable[[str | None], str]:
    return APIKeyValidator(settings.client_api_keys)


def require_miner_key() -> Callable[[str | None], str]:
    return APIKeyValidator(settings.miner_api_keys)


def require_admin_key() -> Callable[[str | None], str]:
    return APIKeyValidator(settings.admin_api_keys)
