"""Trading service test configuration.

trading_service.main reads TRADING_API_KEY into a module constant at import time, so the
test key must be set before the app is first imported. The client fixtures below also set
the matching header by default so authenticated route tests can run unchanged.
"""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TRADING_API_KEY", "test-trading-key")


@pytest.fixture
def client():
    """Authenticated TestClient for the Trading service."""
    from trading_service.main import app

    return TestClient(app, headers={"X-Trading-Api-Key": "test-trading-key"})
