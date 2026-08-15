"""Conftest for the GPU service tests — builds the schema this suite needs.

The database itself is already a throwaway: the repo-root conftest points `AITBC_DATA_DIR` at
a temporary directory, so `gpu_service.storage` resolves to a file under it rather than to
`/var/lib/aitbc/data/gpu_service.db`, which is what the suite ran against until V23-73.

It still has no *tables*, though. `init_db()` runs in the FastAPI lifespan, and a bare
`TestClient(app)` never triggers it — the suite only ever had a schema because the deployed
database already had one, which is also why `test_get_consumer_gpu_profiles` passed here and
would have failed on a clean machine.
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

    from gpu_service import storage

    asyncio.run(storage.init_db())
