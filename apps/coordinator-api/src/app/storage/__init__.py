"""Persistence helpers for the coordinator API."""

from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session

from .db import get_session, init_db

# Concrete dependency annotation for FastAPI/Pydantic
SessionDep = Annotated[Session, Depends(get_session)]

__all__ = ["SessionDep", "get_session", "init_db"]
