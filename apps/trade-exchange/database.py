#!/usr/bin/env python3
"""
Database configuration for the AITBC Trade Exchange
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from models import Base

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./exchange.db")

# Create engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False  # Set to True for SQL logging
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
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency for FastAPI
def get_db_session():
    """Get database session for FastAPI dependency"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Don't close here, let the caller handle it
