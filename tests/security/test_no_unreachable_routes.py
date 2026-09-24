"""No route a service registers may be unreachable behind another one.

Starlette matches routes in **declaration order** and stops at the first full
match. Two consequences, both of which this repository has shipped:

* a static path declared after a parameterized path that matches it never runs --
  ``GET /identities/search`` binds ``agent_id="search"`` and is answered by
  ``get_agent_identity``;
* the same path registered twice is answered by whichever router was included
  first -- ``/v1/protected/admin`` existed in two modules, and the published
  OpenAPI document described the copy that never ran.

Neither failure produces a routing error. The caller gets a plausible answer from
the wrong handler, usually a 404 that reads like "no such record", which is why
both survived review and why one of them was even pinned by a passing test
(``test_routers_bounty.py`` asserted ``data["bounty_id"] == "stats"``).

**This asks the live router, not the source.** An AST scan over decorators finds
the first kind and is blind to the second, because a duplicate path only appears
once two routers have been mounted under the same prefix. Building the real app
is the only check that sees both.

What it does not cover: a router mounted behind a feature flag that is off in the
test environment is not inspected, and a router never passed to
``include_router()`` at all contributes no routes and so cannot be shadowed --
that is a separate defect this file deliberately says nothing about.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.routing import Match

REPO = Path(__file__).resolve().parents[2]

# Throwaway values so import-time Settings validation passes. Nothing here binds a
# socket or opens a database: every one of these services does that inside its
# lifespan, which building the app does not run.
os.environ.setdefault("NODE_ENV", "test")
os.environ.setdefault("SECRET_KEY", "x" * 48)
os.environ.setdefault("JWT_SECRET", "y" * 48)

# (service, package root relative to the repo, module, attribute holding the app)
SERVICES = [
    ("coordinator-api", "apps/coordinator-api/src", "coordinator_api.main", "create_app"),
    ("api-gateway", "apps/api-gateway/src", "api_gateway.main", "app"),
    ("market", "apps/market/src", "market_service.main", "app"),
    ("agent-coordinator", "apps/agent-coordinator/src", "agent_app.main", "app"),
    ("blockchain-node", "apps/blockchain-node/src", "aitbc_chain.app", "create_app"),
]


def _build(src_dir: str, module: str, attr: str) -> FastAPI:
    root = REPO / src_dir
    # A rename that moves a service out from under SERVICES must fail loudly here.
    # Skipping the entry would quietly drop a whole service from the check.
    assert root.is_dir(), f"{src_dir} does not exist; SERVICES is stale, update it"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    obj = getattr(__import__(module, fromlist=["*"]), attr)
    return obj if isinstance(obj, FastAPI) else obj()


def unreachable(app: FastAPI) -> list[tuple[str, str, str, str]]:
    """Every route the router can never dispatch to, as (method, path, dead, winner)."""
    routes = [r for r in app.routes if hasattr(r, "path_format") and hasattr(r, "endpoint")]
    out = []
    for route in routes:
        if "{" in route.path_format:
            continue  # a parameterized path has no single concrete path to probe
        for method in sorted(getattr(route, "methods", None) or []):
            if method in ("HEAD", "OPTIONS"):
                continue
            scope: dict[str, Any] = {
                "type": "http",
                "method": method,
                "path": route.path_format,
                "path_params": {},
                "root_path": "",
                "headers": [],
            }
            for other in routes:
                if other.matches(scope)[0] != Match.FULL:
                    continue
                if other is not route:
                    out.append((method, route.path_format, _name(route), _name(other)))
                break
    return out


def _name(route: Any) -> str:
    endpoint = route.endpoint
    module = getattr(endpoint, "__module__", "?").rsplit(".", 1)[-1]
    return f"{module}.{getattr(endpoint, '__name__', '?')}()"


@pytest.mark.parametrize(("service", "src_dir", "module", "attr"), SERVICES, ids=[s[0] for s in SERVICES])
def test_no_route_is_unreachable(service: str, src_dir: str, module: str, attr: str) -> None:
    """An import failure here is a failure, not a skip -- a guard that opts out is not a guard."""
    app = _build(src_dir, module, attr)
    routes = [r for r in app.routes if hasattr(r, "endpoint")]
    assert routes, f"{service} built no routes at all; the check below would be vacuous"

    dead = unreachable(app)
    assert not dead, "\n".join(
        [f"{service}: {len(dead)} route(s) can never be reached:"]
        + [f"  {m:6s} {p}\n      declared {a}\n      answered by {b}" for m, p, a, b in dead]
    )


def test_detector_catches_a_static_path_shadowed_by_a_parameter() -> None:
    """Without this, a refactor that broke `unreachable()` would leave five silent passes."""
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def get_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @app.get("/items/search")
    async def search_items() -> dict[str, str]:
        return {"ok": "yes"}

    found = unreachable(app)
    assert [(m, p) for m, p, _, _ in found] == [("GET", "/items/search")]
    assert "get_item()" in found[0][3]


def test_detector_catches_a_path_registered_twice() -> None:
    """The AST-based version of this check cannot see this case at all."""
    app = FastAPI()

    @app.get("/admin")
    async def first() -> dict[str, str]:
        return {"which": "first"}

    @app.get("/admin")
    async def second() -> dict[str, str]:
        return {"which": "second"}

    found = unreachable(app)
    assert [(m, p) for m, p, _, _ in found] == [("GET", "/admin")]
    assert "second()" in found[0][2] and "first()" in found[0][3]


def test_detector_does_not_flag_a_correctly_ordered_router() -> None:
    """The same two paths in the other order are both reachable."""
    app = FastAPI()

    @app.get("/items/search")
    async def search_items() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/items/{item_id}")
    async def get_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    assert unreachable(app) == []
