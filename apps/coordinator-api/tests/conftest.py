"""Ensure coordinator-api src is on sys.path for all tests in this directory."""

import os
import sys
from pathlib import Path

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")

# Remove any stale 'app' module loaded from a different package so the
# coordinator 'app' resolves correctly.
_app_mod = sys.modules.get("app")
if _app_mod and hasattr(_app_mod, "__file__") and _app_mod.__file__ and _src not in str(_app_mod.__file__):
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]

if _src not in sys.path:
    sys.path.insert(0, _src)

# Set up test environment
os.environ["TEST_MODE"] = "true"
project_root = Path(__file__).resolve().parent.parent.parent
os.environ["AUDIT_LOG_DIR"] = str(project_root / "logs" / "audit")
os.environ["TEST_DATABASE_URL"] = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    from sqlmodel import Session, SQLModel, create_engine
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(scope="function")
def client():
    """Create a TestClient for API testing."""
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)
