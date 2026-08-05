import pytest


@pytest.fixture(autouse=True)
def _reset_edge_clients():
    """Reset any module-level client state between tests."""
    yield
