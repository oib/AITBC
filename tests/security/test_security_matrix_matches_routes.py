"""Every public entry in the route security matrix must name a path the app serves.

``AuthMiddleware`` consults ``ROUTE_SECURITY_MATRIX`` before the router runs, and
``get_auth_level`` returns ``DENY`` for anything unregistered ("Unregistered routes
default to deny (CORE-03)"). So a matrix entry whose path the app does not serve is
worse than dead weight: the real path it was written for is still unregistered, and
therefore still closed. **A public entry pointing at nothing means the endpoint it
was meant to open answers 401 to everyone.**

That is not hypothetical. Until 2026-09-24 the matrix carried ``/v1/health``,
``/v1/health/live`` and ``/v1/health/ready`` -- paths no service has ever served --
while coordinator-api's own liveness and readiness probes, declared at
``/health/live`` and ``/health/ready`` and tagged "health", had no entry at all.
Both answered 401 on the running fleet. ``curl -s`` exits 0 on a 401 exactly as it
does on a 404, so a probe written the usual way would have reported the service
ready against that. ``tests/unit/test_v2399_health_gate_paths.py`` records the same
``/v1`` drift in the scripts and runbooks and fixed it there; it outlived that
cleanup in the matrix because nothing had ever compared the matrix to a route table.

Scope, and what this deliberately does not check:

* **Only coordinator-api.** It is the one deployed service that installs
  ``AuthMiddleware``; everywhere else this matrix is inert.
* **Only ``AuthLevel.NONE`` entries.** A restrictive entry naming an unserved path
  closes nothing that was open, so it is untidy rather than dangerous.
* **Only wildcard-free entries.** ``/v1/security*`` and friends legitimately
  describe route families that are not mounted today.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI

os.environ.setdefault("NODE_ENV", "test")
os.environ.setdefault("SECRET_KEY", "x" * 48)
os.environ.setdefault("JWT_SECRET", "y" * 48)

from aitbc.auth.security_matrix import ROUTE_SECURITY_MATRIX, AuthLevel, get_auth_level  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "apps" / "coordinator-api" / "src"

# /docs and /redoc are registered only when settings.debug is set, so a default
# build does not serve them and that is correct rather than drift.
# test_the_docs_exemption_is_still_conditional pins the reason, so this exemption
# cannot quietly outlive it.
DEBUG_ONLY = {"/docs", "/redoc"}

# The probes the app declares. Public on purpose: they carry no more than /health
# already does, and a gated probe is an unreachable one.
PROBE_PATHS = ["/health", "/health/live", "/health/ready"]


def _app() -> FastAPI:
    # A rename that moves coordinator-api must fail loudly here rather than as an
    # import traceback three frames down.
    assert SRC.is_dir(), f"{SRC} does not exist; this test's path is stale, update it"
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from coordinator_api.main import create_app

    return create_app()


def _served(app: FastAPI) -> set[str]:
    return {r.path_format for r in app.routes if hasattr(r, "path_format")}


def _is_served(path: str, served: set[str]) -> bool:
    """True if some route answers this literal path, directly or via a parameter."""
    if path in served:
        return True
    for route in served:
        if "{" not in route:
            continue
        pattern = "/".join("[^/]+" if segment.startswith("{") else re.escape(segment) for segment in route.split("/"))
        if re.fullmatch(pattern, path):
            return True
    return False


def phantom_public_entries(matrix: dict[str, AuthLevel], served: set[str]) -> list[str]:
    """Public matrix paths that nothing serves -- see the module docstring."""
    return sorted(
        path
        for path, level in matrix.items()
        if level is AuthLevel.NONE and "*" not in path and path not in DEBUG_ONLY and not _is_served(path, served)
    )


def test_no_public_matrix_entry_names_an_unserved_path() -> None:
    served = _served(_app())
    assert served, "the app built no routes at all; the check below would be vacuous"
    phantom = phantom_public_entries(ROUTE_SECURITY_MATRIX, served)
    assert not phantom, (
        "these matrix paths are AuthLevel.NONE but nothing serves them, so whatever "
        f"they were written to open is still deny-by-default: {phantom}"
    )


@pytest.mark.parametrize("path", PROBE_PATHS)
def test_the_declared_probes_are_public(path: str) -> None:
    # The positive half. Deleting the matrix entries outright would leave the test
    # above green, because an unserved entry and a missing entry both read as
    # "not phantom".
    assert path in _served(_app()), f"{path} is no longer served; update PROBE_PATHS"
    level = get_auth_level(path)
    assert level is AuthLevel.NONE, (
        f"{path} resolves to {level.name}; AuthMiddleware answers before the handler "
        "runs, so the probe is unreachable no matter what the handler does"
    )


def test_the_docs_exemption_is_still_conditional() -> None:
    app = _app()
    assert app.docs_url is None and app.redoc_url is None, (
        "/docs and /redoc are served unconditionally now, so they are no longer a "
        "documented exception -- drop them from DEBUG_ONLY"
    )


def test_detector_catches_a_public_entry_for_an_unserved_path() -> None:
    served = {"/health", "/v1/blocks/{block_id}"}
    matrix = {
        "/health": AuthLevel.NONE,
        "/v1/blocks/7": AuthLevel.NONE,  # served by the parameterized route
        "/v1/gone": AuthLevel.NONE,
        "/v1/also-gone": AuthLevel.ADMIN,  # restrictive, so not this test's business
        "/v1/wild*": AuthLevel.NONE,  # wildcard, deliberately out of scope
    }
    assert phantom_public_entries(matrix, served) == ["/v1/gone"]
