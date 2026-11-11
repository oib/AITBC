"""Make this app importable without disturbing how the rest of the suite is named.

`main.py`, `chain_client.py` and `routers/` live at the app root rather than under `src/`, so the app directory
has to be on `sys.path` for the tests to import them at all.

Two things keep that safe, and both matter (V23-69):

- The entry inserted is the *app* directory, never `apps/`. `apps/` is an ancestor of every
  app's test directory, so putting it on `sys.path` changes the module name pytest derives for
  every other suite and gets one conftest imported twice under two names.
- This `tests/` directory is deliberately not a package. With the app directory on `sys.path`
  and an `__init__.py` here, pytest would name these modules `tests.test_...` — colliding with
  the repo-root `tests` package, which is already in `sys.modules`.

This suite is the sole remaining bare-`main` claimant in the repo: the test
modules do `from main import app`, which resolves through `_APP_ROOT` above.
That is safe only because every other root-layout app loads its `main.py`
under a unique spec name (apps/ffmpeg, apps/whisper, apps/hermes_agent,
apps/ollama_gate — see #1657). Do not add another bare `import main` /
`from main import` in a sibling app's tests; spec-load it instead, or the
first importer wins `sys.modules["main"]` and the loser gets the wrong
FastAPI app.
"""

import os
import sys
from pathlib import Path

# The suite runs as a configured service: chain-id resolution fails loudly
# without one since #307, so tests pin an explicit test id up front.
os.environ.setdefault("CHAIN_ID", "ait-testchain")

# #1745 added an in-app rate limit (EXPLORER_RATE_LIMIT, default 120/minute).
# Pin a small budget here — read *before* ``main`` is imported by the test
# modules — so the trip test needs only a handful of requests; the autouse
# fixture below disables enforcement for every other test in the suite.
os.environ.setdefault("EXPLORER_RATE_LIMIT", "5/minute")

_APP_ROOT = str(Path(__file__).resolve().parent.parent)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _rate_limiting_off(monkeypatch) -> None:
    """Disable the in-app rate limiter for this suite — and only for it.

    Same pattern as apps/coordinator-api/tests/conftest.py (#1657): every
    TestClient request keys on the same "testclient" peer, so suites that
    page through endpoints repeatedly would trip 429s. ``monkeypatch``
    restores the previous value after each test; the flag is read per
    request by RateLimitMiddleware.dispatch, so a test that sets
    ``AITBC_ENABLE_RATE_LIMITING=true`` still exercises the limiter.
    """
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
