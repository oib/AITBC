"""Tests for the SQL-backed consent store."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlmodel import SQLModel

from aitbc.compliance.consent import ConsentTracker
from coordinator_api.contexts.compliance.services.consent_store import SQLConsentStore
from coordinator_api.storage import db as _db_module

get_engine = _db_module.get_engine


@pytest.fixture(scope="function", autouse=True)
def _db(monkeypatch):
    """Create the consent_record table for each test and restore environment after."""
    db_path = f"/tmp/aitbc_sql_consent_test_{uuid.uuid4().hex}.db"
    db_url = f"sqlite:///{db_path}"

    original_database_url = os.environ.get("DATABASE_URL")
    original_database_adapter = os.environ.get("DATABASE_ADAPTER")

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_ADAPTER", "sqlite")

    # Force get_engine() to build a fresh engine for this test's DATABASE_URL.
    _db_module._engine = None
    _db_module._async_engine = None

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    SQLModel.metadata.create_all(engine)

    yield

    if original_database_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = original_database_url
    if original_database_adapter is None:
        os.environ.pop("DATABASE_ADAPTER", None)
    else:
        os.environ["DATABASE_ADAPTER"] = original_database_adapter

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
