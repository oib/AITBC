"""The mock blockchain node must serve routes the real blockchain node serves.

V23-42. `tests/fixtures/mock_blockchain_node.py` served `/rpc/getBalance/{address}`,
`/rpc/admin/mintFaucet` and `/rpc/sendTx`. The real node has never had any of the three; it
has `/rpc/balance/{address}`, `/rpc/faucet` and `/rpc/transaction`, with different response
shapes. The mock had been written to match a *client* rather than the server, so the client
and the mock agreed with each other while neither agreed with the thing they stand in for.

A mock that does not match its subject is worse than no mock: it converts a 404 in production
into a green test. This pins the correspondence.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

MOCK = Path(__file__).resolve().parents[1] / "fixtures" / "mock_blockchain_node.py"

# Served by FastAPI itself on any app, so they are not part of the node's declared routes.
FRAMEWORK_ROUTES = {"/openapi.json", "/docs", "/redoc"}


def _placeholders(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def _mock_routes() -> set[tuple[str, str]]:
    """(METHOD, path) for every route the mock declares, read from its source."""
    tree = ast.parse(MOCK.read_text(encoding="utf-8"))
    routes = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.args
                and isinstance(dec.args[0], ast.Constant)
            ):
                routes.add((dec.func.attr.upper(), _placeholders(str(dec.args[0].value))))
    return routes


def _node_routes() -> set[tuple[str, str]]:
    """(METHOD, path) for the real node, built by import — no running node needed."""
    pytest.importorskip("aitbc_chain", reason="blockchain-node not importable")
    from aitbc_chain.rpc.router import router

    return {
        (method, _placeholders(f"/rpc{route.path}"))
        for route in router.routes
        for method in getattr(route, "methods", set()) or set()
    }


def test_mock_declares_routes():
    """A parser finding nothing would make the assertion below vacuous."""
    assert len(_mock_routes()) >= 5, f"parsed {_mock_routes()} from {MOCK.name}"


def test_every_mock_route_exists_on_the_real_node():
    mock = {(m, p) for m, p in _mock_routes() if p not in FRAMEWORK_ROUTES and p != "/health"}
    node = _node_routes()
    invented = sorted(f"{m} {p}" for m, p in mock if (m, p) not in node)
    assert not invented, (
        f"the mock serves {invented}, which the real node does not.\n"
        f"Point the mock at the real route and match its response shape — a mock that answers "
        f"a URL the server 404s turns a production failure into a passing test."
    )
