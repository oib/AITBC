"""
CLI integration tests using AITBC CLI against a live (in-memory) coordinator.

Spins up the real coordinator FastAPI app with an in-memory SQLite DB,
then patches httpx.Client so every CLI command's HTTP call is routed
through the ASGI transport instead of making real network requests.
"""

import sys
f