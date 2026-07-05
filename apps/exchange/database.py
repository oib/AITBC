#!/usr/bin/env python3
"""
Database configuration for the AITBC Trade Exchange
"""

import os

from models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from aitbc.constants import DATA_DIR

# Database configuration
DATABASE_URL = os.getenv("EXCHANGE_DATABASE_URL", f"sqlite:///{DATA_DIR}/data/exchange/exchange.db")

# Create engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,  # Set to True for SQL logging
    )
else:
    engine = create_engine(DATABASE_URL, echo=False)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Create tables
def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get database session (FastAPI dependency generator).

    Yields a session and ensures it is closed after the request, preventing
    connection leaks. Use as ``db: Annotated[Session, Depends(get_db)]``.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
