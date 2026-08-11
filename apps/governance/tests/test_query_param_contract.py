"""Query/body parameter contracts on the governance router.

Two defects of the same family, both surfacing as a 422 the caller cannot avoid:

* **List endpoints demanded their own filters.** ``role: str | None`` with no default
  is a *required* query parameter in FastAPI — Optional describes the type, not the
  requirement. ``GET /v1/governance/profiles`` and four siblings answered 422 unless
  every filter was supplied, so the listing endpoints could not list. The service layer
  had defaulted each filter to ``None`` and guarded it with ``if role:`` all along; only
  the router disagreed. ``get_analytics`` proved the intent on its own — its body reads
  ``period or "monthly"``, a default no caller could ever reach.

* **POST payloads were read from the query string.** FastAPI treats bare scalar
  parameters as query parameters, so ``/v1/governance/stake`` and
  ``/v1/governance/delegate`` wanted their payload in the URL while their only caller —
  ``aitbc governance stake`` / ``delegate`` in ``cli/aitbc_cli/commands/operations.py``
  — posts JSON. Every invocation got a 422. The consumer settles the design question.

The AST guard at the bottom is the part that keeps this closed: the behavioural tests
below only cover the endpoints that exist today, and this defect arrives by someone
adding a sixth one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from governance_service.main import app

_MAIN = Path(__file__).resolve().parent.parent / "src" / "governance_service" / "main.py"

LIST_ENDPOINTS = [
    "/v1/governance/profiles",
    "/v1/governance/proposals",
    "/v1/governance/votes",
    "/v1/governance/analytics",
    "/v1/transactions",
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("path", LIST_ENDPOINTS)
def test_list_endpoints_are_callable_without_filters(client: TestClient, path: str) -> None:
    """No filter is mandatory.

    Asserted as "not 422" rather than "200": these endpoints read the database, and a
    missing table is a different failure from an unsatisfiable request contract. 422 is
    the only status that means "you did not send enough", which is the defect.
    """
    assert client.get(path).status_code != 422


def test_filters_are_still_applied(client: TestClient) -> None:
    """Non-vacuous: defaulting the parameters must not have stopped them working."""
    assert client.get("/v1/governance/analytics", params={"period": "weekly"}).json()["period"] == "weekly"
    assert client.get("/v1/governance/analytics").json()["period"] == "monthly"


def test_stake_accepts_the_body_the_cli_sends(client: TestClient) -> None:
    """Payload copied from cli/aitbc_cli/commands/operations.py:652."""
    response = client.post(
        "/v1/governance/stake",
        json={"staker_address": "0x1234567890abcdef", "amount": 1000, "lock_period_days": 30},
    )
    assert response.status_code != 422


def test_delegate_accepts_the_body_the_cli_sends(client: TestClient) -> None:
    """Payload copied from cli/aitbc_cli/commands/operations.py:679."""
    response = client.post(
        "/v1/governance/delegate",
        json={
            "delegator_address": "0x1234567890abcdef",
            "delegate_address": "0xfedcba0987654321",
            "amount": 1000,
        },
    )
    assert response.status_code != 422


def test_stake_still_rejects_a_malformed_body(client: TestClient) -> None:
    """The guard must be able to fail: a missing required field is still a 422."""
    assert client.post("/v1/governance/stake", json={"staker_address": "0x1"}).status_code == 422


def _route_handlers() -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(_MAIN.read_text())
    handlers = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        decorators = [ast.unparse(d) for d in node.decorator_list]
        if any(f"app.{verb}(" in d for d in decorators for verb in ("get", "post", "put", "delete", "patch")):
            handlers.append(node)
    return handlers


def test_no_optional_route_parameter_is_declared_without_a_default() -> None:
    """An Optional parameter with no default is a required parameter.

    This is the enforceable check the behavioural tests cannot provide, because it
    covers endpoints that do not exist yet.
    """
    offenders = []
    for handler in _route_handlers():
        args = handler.args.args + handler.args.kwonlyargs
        defaults = handler.args.defaults + [d for d in handler.args.kw_defaults if d is not None]
        for arg in args[: len(handler.args.args) - len(handler.args.defaults)]:
            if arg.annotation is None:
                continue
            annotation = ast.unparse(arg.annotation)
            # Annotated[...] carries Depends() and friends, which supply their own value.
            if "None" in annotation and "Annotated" not in annotation:
                offenders.append(f"{handler.name}({arg.arg}: {annotation}) at line {handler.lineno}")
        del defaults

    assert not offenders, (
        "Optional route parameters declared without a default are required parameters. "
        "Add `= None`:\n  " + "\n  ".join(offenders)
    )
