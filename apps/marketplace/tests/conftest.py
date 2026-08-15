"""Conftest for the Marketplace service tests — builds the schema this suite needs.

The database is already a throwaway: the repo-root conftest points `AITBC_DATA_DIR` at a
temporary directory, so `marketplace_service.storage` resolves to a file under it rather than
to `/var/lib/aitbc/data/marketplace_service.db`, which is what the suite ran against — and ran
`create_all` on — until V23-73.

The tables still have to be created. `init_db()` runs in the FastAPI lifespan, which a bare
`TestClient(app)` never triggers.
"""

import sys
from pathlib import Path

import pytest

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Create this service's tables before the first test."""
    import asyncio

    from marketplace_service import storage

    asyncio.run(storage.init_db())
