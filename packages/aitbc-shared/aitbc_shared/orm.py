"""
Shared ORM Configuration
Provides shared declarative_base and session handling for AITBC applications
"""

from sqlmodel import Session, SQLModel, create_engine

# Shared engine - can be configured per application
_engine = None


def get_engine(database_url: str | None = None):
    """Get or create the shared database engine"""
    global _engine
    if _engine is None:
        if database_url is None:
            database_url = "sqlite:///aitbc.db"
        _engine = create_engine(database_url, echo=False)
    return _engine


def get_session(database_url: str | None = None):
    """Get a database session"""
    engine = get_engine(database_url)
    with Session(engine) as session:
        yield session


def init_db(database_url: str | None = None):
    """Initialize the database with all shared models"""

    engine = get_engine(database_url)
    SQLModel.metadata.create_all(engine)
