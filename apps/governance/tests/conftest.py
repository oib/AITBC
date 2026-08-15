"""Conftest for governance service tests — adds src to sys.path and isolates the database.

``storage.py`` builds its engine at import time, resolving ``governance_service.db`` under
``DATA_DIR``. That used to be the deployed machine's ``/var/lib/aitbc``, so running the suite
read and wrote the live database: an active ``aitbc-governance`` unit serves it, ``init_db()``
ran ``create_all`` against it, and any test creating a profile, proposal or vote left real
rows behind. It also made results depend on whatever schema that host happened to have, which
is what made ``test_get_governance_proposals`` fail with a 500 locally and pass in CI.

The repo-root conftest now points ``AITBC_DATA_DIR`` at a temporary directory, which moves
this service's database along with every other one (V23-73). What is left here is the ``DB_TYPE``
reset — the deployed unit may set it to ``postgresql``, and this suite is SQLite — and building
the schema, which nothing else does.
"""

import os
import sys
from pathlib import Path

import pytest

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

os.environ.pop("DB_TYPE", None)


@pytest.fixture
def test_database_path() -> Path:
    """Filesystem path of the throwaway database, for tests that seed rows directly."""
    from aitbc.constants import DATA_DIR

    return DATA_DIR / "data" / "governance_service.db"


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Create this service's tables before the first test.

    ``init_db()`` runs in the FastAPI lifespan, which a bare ``TestClient(app)`` never
    triggers — the suite only ever had tables because it was pointed at a database
    someone else had already populated.
    """
    import asyncio

    from governance_service import storage

    asyncio.run(storage.init_db())
