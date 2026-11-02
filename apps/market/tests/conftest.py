"""Conftest for the Market service tests — builds the schema this suite needs.

The database is already a throwaway: the repo-root conftest points `AITBC_DATA_DIR` at a
temporary directory, so `market_service.storage` resolves to a file under it rather than
to `/var/lib/aitbc/data/marketplace_service.db`, which is what the suite ran against — and ran
`create_all` on — until V23-73.

The tables still have to be created. `init_db()` runs in the FastAPI lifespan, which a bare
`TestClient(app)` never triggers.
"""

import os
import sys
from pathlib import Path

import pytest

# V23-74: the deployed node may set DATABASE_URL/DB_TYPE to point at a live database.
# Pop them so the test suite builds its own throwaway SQLite+aiosqlite database.
os.environ.pop("DATABASE_URL", None)
os.environ.pop("DB_TYPE", None)
# The suite runs as a configured service: default_chain_id no longer
# substitutes a literal chain since #307, so tests pin an explicit test id.
# CHAIN_ID feeds the strict resolver; DEFAULT_CHAIN_ID must stay unset so the
# settings field keeps its empty default (the v066 config tests assert that).
os.environ.setdefault("CHAIN_ID", "ait-testchain")

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Create this service's tables before the first test."""
    import asyncio

    from market_service import storage

    asyncio.run(storage.init_db())


@pytest.fixture(autouse=True)
def _auth_disabled_for_tests(request):
    """Route tests exercise handler behaviour, not the key gate.

    The mutating routes are API-key gated (#813); the suite disables the
    authenticator per test so legacy callers keep working. Modules that
    test the gate itself opt out by name.
    """
    if request.module.__name__.split(".")[-1] in {"test_market_auth_missing", "test_access_secret_hashing"}:
        yield
        return
    from market_service.main import require_market_api_key

    old = require_market_api_key.auth_enabled
    require_market_api_key.auth_enabled = False
    try:
        yield
    finally:
        require_market_api_key.auth_enabled = old
