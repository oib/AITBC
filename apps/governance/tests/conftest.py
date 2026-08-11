"""Conftest for governance service tests — adds src to sys.path and isolates the database.

``storage.py`` builds its engine at import time from ``DATABASE_URL``, defaulting to
``/var/lib/aitbc/data/governance_service.db`` — the **deployed** service's database.
Until this file set the variable, running the suite read and wrote that file: an active
``aitbc-governance`` unit serves it, ``init_db()`` ran ``create_all`` against it, and any
test creating a profile, proposal or vote left real rows behind. It also made results
depend on whatever schema that host happened to have, which is what made
``test_get_governance_proposals`` fail with a 500 locally and pass in CI.

The assignment has to happen at import time, before any test module imports
``governance_service.storage`` and triggers ``engine = _create_engine()``. pytest imports
conftest first, so module scope is the correct place; a fixture would be too late.
"""

import os
import sys
import tempfile
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Bound to the session: the file is created here, torn down by _cleanup_test_database below.
_TEST_DB = Path(tempfile.mkdtemp(prefix="governance-tests-")) / "governance_service.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB}"
os.environ.pop("DB_TYPE", None)

import pytest  # noqa: E402  — must follow the environment assignment above


@pytest.fixture
def test_database_path() -> Path:
    """Filesystem path of the throwaway database, for tests that seed rows directly."""
    return _TEST_DB


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Create the schema up front, and remove the database once the session ends.

    ``init_db()`` runs in the FastAPI lifespan, which a bare ``TestClient(app)`` never
    triggers — the suite only ever had tables because it was pointed at a database
    someone else had already populated.
    """
    import asyncio

    from governance_service import storage

    asyncio.run(storage.init_db())
    yield
    try:
        _TEST_DB.unlink(missing_ok=True)
        _TEST_DB.parent.rmdir()
    except OSError:
        pass
