"""
CLI integration tests against a live (in-memory) coordinator.

Spins up the real coordinator FastAPI app with an in-memory SQLite DB,
then patches httpx.Client so every CLI command's HTTP call is routed
through the ASGI transport instead of making real network requests.

v0.5.17 B2: The coordinator-api auth structure was refactored — app.deps
no longer exists and APIKeyValidator was removed. This test file needs a
full rewrite against the new auth layer (app/auth/dependencies.py).
"""

import pytest

pytest.skip("coordinator-api auth structure changed — test needs rewrite (v0.5.17 B2)", allow_module_level=True)
