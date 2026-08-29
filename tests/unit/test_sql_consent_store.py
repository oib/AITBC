"""Tests for the SQL-backed consent store."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlmodel import SQLModel

os.environ["DATABASE_URL"] = f"sqlite:////tmp/aitbc_sql_consent_test_{uuid.uuid4().hex}.db"
os.environ["DATABASE_ADAPTER"] = "sqlite"

from aitbc.compliance.consent import ConsentTracker
from coordinator_api.contexts.compliance.services.consent_store import SQLConsentStore
from coordinator_api.storage.db import get_engine


@pytest.fixture(scope="module", autouse=True)
def _db():
    """Create the consent_record table for the test module."""
    db_path = os.environ["DATABASE_URL"].replace("sqlite://", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    yield
    try:
        Path(db_path).unlink(missing_ok=True)
    except OSError:
        pass


def test_sql_consent_store_round_trip() -> None:
    """A consent record can be persisted and retrieved."""
    tracker = ConsentTracker(store=SQLConsentStore())
    record = tracker.grant("patient-1", "treatment")
    assert record is not None
    assert record.granted is True

    found = tracker.is_consented("patient-1", "treatment")
    assert found is True

    tracker.revoke("patient-1", "treatment")
    after_revoke = tracker.is_consented("patient-1", "treatment")
    assert after_revoke is False
