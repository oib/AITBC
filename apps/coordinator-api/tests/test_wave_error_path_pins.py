"""Error-path pins for the #1510 bounded-list wave (Coder: B).

``fix(coordinator-api): bound pure-SQL list endpoints at limit<=1000`` gave
three GET endpoints a ``limit`` query param declared ``Query(ge=1, le=1000)``:

* ``GET /v1/agents/workflows``
* ``GET /v1/agent-creativity/capabilities/{agent_id}``
* ``GET /v1/trading/requests/{request_id}/matches``

The rejection branch FastAPI generates for out-of-range or non-integer
``limit`` values (422) had no coverage — these pins hold it, plus the
boundary values that must still pass validation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token


def _admin() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('admin-1', 'admin')}"}


BOUNDED_LIST_ENDPOINTS = [
    ("/v1/agents/workflows", _admin()),
    ("/v1/agent-creativity/capabilities/agent-x", _admin()),
    # #1876 bound the trading read surface: the handler now takes
    # AdminOrClientDep + agent-ownership scoping, so it needs a token.
    ("/v1/trading/requests/req-x/matches", _admin()),
]


@pytest.mark.parametrize("path,headers", BOUNDED_LIST_ENDPOINTS, ids=lambda v: v if isinstance(v, str) else "")
@pytest.mark.parametrize("limit", ["0", "-1", "1001", "abc", "1.5"])
def test_out_of_range_limit_is_422(client: TestClient, path: str, headers: dict[str, str], limit: str) -> None:
    """limit outside [1, 1000] or non-integer -> FastAPI request validation 422."""
    resp = client.get(path, params={"limit": limit}, headers=headers)
    assert resp.status_code == 422, f"{path}?limit={limit} answered {resp.status_code}"


@pytest.mark.parametrize("path,headers", BOUNDED_LIST_ENDPOINTS, ids=lambda v: v if isinstance(v, str) else "")
@pytest.mark.parametrize("limit", ["1", "200", "1000"])
def test_in_range_limit_passes_validation(client: TestClient, path: str, headers: dict[str, str], limit: str) -> None:
    """Boundary values must reach the handler — never a validation 422."""
    resp = client.get(path, params={"limit": limit}, headers=headers)
    assert resp.status_code != 422, f"{path}?limit={limit} answered {resp.status_code}"


def test_limit_absent_uses_default(client: TestClient) -> None:
    """No limit param -> default 200 applies; endpoints still answer."""
    for path, headers in BOUNDED_LIST_ENDPOINTS:
        resp = client.get(path, headers=headers)
        assert resp.status_code == 200, f"{path} answered {resp.status_code}: {resp.text[:200]}"
