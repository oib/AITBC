"""Persistence helpers for the coordinator API."""

from typing import Annotated
from sqlalchemy.orm import Session
from fastapi import Depends
from .db import get_session, init_db

SessionDep = Annotated[Session, Depends(get_session)]

__all__ = ["get_session", "init_db", "SessionDep"]
